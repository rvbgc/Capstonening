import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sync_threat_feed import CACHE_PATH, FEED_URL, MAX_BYTES


URL_PATTERN = re.compile(r"""https?://[^\s<>"']+""", re.IGNORECASE)

# Top-level domains accepted for links written without http:// or https://.
# A fixed list avoids treating ordinary text such as "today.Please" as a link.
BARE_LINK_TLDS = (
    "app|asia|biz|buzz|cc|cf|click|club|cn|co|com|cyou|ga|gd|gov|gq|icu|"
    "info|io|is|lat|link|live|love|ly|makeup|me|ml|mobi|net|online|org|ph|"
    "pw|ru|shop|site|store|su|tk|to|top|vip|win|ws|xyz"
)

BARE_LINK_PATTERN = re.compile(
    r"(?<![@\w.-])"                                  # not part of an email
    r"((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"   # labels, e.g. globe-phl2i.
    r"(?:" + BARE_LINK_TLDS + r"))"                   # known top-level domain
    r"(?![\w-])"
    r"(/[^\s<>\"']*)?",                               # optional path
    re.IGNORECASE,
)

TRAILING_PUNCTUATION = ".,;:!?)]}'\""

# Our prototype's cache-expiry policy, not a provider risk rating.
MAX_FEED_AGE_SECONDS = 2 * 60 * 60
MAX_URLS = 10

PROVIDER_FLAGS = (
    "malicious_google",
    "malicious_openphish",
    "malicious_phishtank",
    "malicious_tweetfeed",
    "malicious_urlscan",
)


def _url_key(value):
    """Normalize basic URL structure without removing paths or queries."""
    if not isinstance(value, str) or not value:
        return None

    if any(character.isspace() or ord(character) < 32 for character in value):
        return None

    try:
        parsed = urlsplit(value)

        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None

        hostname = (
            parsed.hostname.rstrip(".")
            .encode("idna")
            .decode("ascii")
            .lower()
        )

        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "https" else 80

        return (
            parsed.scheme,
            hostname,
            port,
            parsed.username,
            parsed.password,
            parsed.path or "/",
            parsed.query,
            parsed.fragment,
        )
    except (ValueError, UnicodeError):
        return None


def _rejoin_split_links(text):
    """Undo line breaks that OCR or narrow message bubbles put inside links."""
    # "https://" at the end of a line, rest of the link on the next line.
    text = re.sub(r"(https?://)\s+(?=\S)", r"\1", text, flags=re.IGNORECASE)

    # "myvips" + newline + ".makeup/vipsbdo" -> "myvips.makeup/vipsbdo"
    text = re.sub(r"(?<=[A-Za-z0-9])[ \t]*\n[ \t]*(?=\.[A-Za-z])", "", text)

    # "https://bit.ly/bdo-" + newline + "canceltransfer"
    # "https://digitalbpi.cc/cancel" + newline + "/1r5t8w3y"
    text = re.sub(
        r"(https?://[^\s<>\"']*(?:-|/))[ \t]*\n[ \t]*(?=[A-Za-z0-9])",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(https?://[^\s<>\"']*[A-Za-z0-9])[ \t]*\n[ \t]*(?=/[A-Za-z0-9])",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    return text


def extract_links(text):
    """Return link candidates as (written, [forms to check]) pairs.

    Complete http(s) URLs are checked as written. Links written without a
    scheme (e.g. "bit.ly/abc" or "globe-phl2i.com") are checked as both
    https:// and http://, because the feed stores complete URLs.
    """
    text = _rejoin_split_links(text)
    links = []
    seen = set()

    def add(written, forms):
        written = written.rstrip(TRAILING_PUNCTUATION)
        if written and written.lower() not in seen:
            seen.add(written.lower())
            links.append((written, forms(written)))

    for match in URL_PATTERN.finditer(text):
        add(match.group(0), lambda url: [url])

    # Remove complete URLs so their domains are not found a second time.
    remaining = URL_PATTERN.sub(" ", text)

    for match in BARE_LINK_PATTERN.finditer(remaining):
        add(
            match.group(0),
            lambda link: ["https://" + link, "http://" + link],
        )

    return links


def check_message_links(text):
    result = {
        "source": "PhishHunt",
        "status": "unavailable",
        "match_scope": "normalized_full_url",
        "feed_fetched_at": None,
        "message": (
            "URL checking is unavailable. "
            "No URL safety assessment was made."
        ),
        "urls": [],
    }

    # Preserve the order and remove repeated identical link candidates.
    links = extract_links(text)

    if not links:
        result.update(
            status="no_urls",
            message=(
                "No web link was recognized in this message. "
                "Obfuscated links (for example with spaces or symbols "
                "inserted) are not checked."
            ),
        )
        return result

    if len(links) > MAX_URLS:
        result.update(
            status="not_checked",
            message="Too many URLs. Check a message with at most 10 URLs.",
        )
        return result

    try:
        with CACHE_PATH.open("rb") as file:
            raw = file.read(MAX_BYTES + 1)

        if len(raw) > MAX_BYTES:
            raise ValueError("The cached feed exceeds the size limit.")

        snapshot = json.loads(raw)

        if not isinstance(snapshot, dict):
            raise ValueError("Invalid snapshot.")

        if snapshot.get("source_url") != FEED_URL:
            raise ValueError("Unexpected feed source.")

        timestamp = snapshot["fetched_at"]
        fetched_at = datetime.fromisoformat(timestamp)

        if fetched_at.tzinfo is None:
            raise ValueError("The feed timestamp needs a timezone.")

        age = (
            datetime.now(timezone.utc) - fetched_at
        ).total_seconds()

        if age < -300:
            raise ValueError("The feed timestamp is in the future.")

        result["feed_fetched_at"] = timestamp

        if age > MAX_FEED_AGE_SECONDS:
            result.update(
                status="stale",
                message=(
                    "Threat data is out of date. "
                    "URL checking is currently unavailable."
                ),
            )
            return result

        entries = snapshot["entries"]

        if not isinstance(entries, list) or not entries:
            raise ValueError("The feed has no usable entries.")

        index = {}

        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Invalid feed entry.")

            key = _url_key(entry.get("url"))
            if key is None:
                raise ValueError("Invalid URL in the cached feed.")

            index.setdefault(key, []).append(entry)

    except (OSError, ValueError, TypeError, KeyError):
        return result

    for url, forms in links:
        keys = [key for key in map(_url_key, forms) if key is not None]

        if not keys:
            result["urls"].append({
                "url": url,
                "status": "not_checked",
                "evidence": [],
            })
            continue

        matches = []
        for key in keys:
            matches.extend(index.get(key, []))
        evidence = []

        # Bound response size while retaining the number of matching records.
        for entry in matches[:3]:
            flags = {
                name: (
                    entry.get(name)
                    if isinstance(entry.get(name), bool)
                    else None
                )
                for name in PROVIDER_FLAGS
            }

            verdict = entry.get("verdict")

            evidence.append({
                "source": "PhishHunt",
                "provider_verdict": (
                    verdict if isinstance(verdict, str) else None
                ),
                "provider_flags": flags,
            })

        result["urls"].append({
            "url": url,
            "scheme_added": forms[0] != url,
            "status": "matched" if matches else "not_listed",
            "matching_records": len(matches),
            "evidence": evidence,
        })

    statuses = {item["status"] for item in result["urls"]}

    if "matched" in statuses:
        result.update(
            status="matched",
            message=(
                "A URL matches PhishHunt's suspicious phishing feed. "
                "Verify the message through official contact details."
            ),
        )
        if "not_checked" in statuses:
            result["message"] += " Some URL candidates could not be checked."

    elif "not_checked" in statuses:
        result.update(
            status="incomplete",
            message=(
                "Some URL candidates could not be checked. "
                "The completed checks do not establish safety."
            ),
        )

    else:
        result.update(
            status="not_listed",
            message=(
                "No recognized URL matched the cached feed. "
                "This does not establish that the links are safe."
            ),
        )

    return result