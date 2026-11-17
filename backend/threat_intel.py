import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sync_threat_feed import CACHE_PATH, FEED_URL, MAX_BYTES


URL_PATTERN = re.compile(r"""https?://[^\s<>"']+""", re.IGNORECASE)

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

    # Preserve the order and remove repeated identical URL candidates.
    urls = list(dict.fromkeys(URL_PATTERN.findall(text)))

    if not urls:
        result.update(
            status="no_urls",
            message=(
                "No complete HTTP(S) URL was recognized. "
                "Plain domains and obfuscated links are not checked."
            ),
        )
        return result

    if len(urls) > MAX_URLS:
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

    for url in urls:
        key = _url_key(url)

        if key is None:
            result["urls"].append({
                "url": url,
                "status": "not_checked",
                "evidence": [],
            })
            continue

        matches = index.get(key, [])
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