import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)


FEED_URL = "https://phishunt.io/feed.json"
MAX_BYTES = 10 * 1024 * 1024  # Maximum download: 10 MiB.

CACHE_PATH = Path(
    r"C:\dev\smishguard-data\threat_intelligence"
) / "phishunt_snapshot.json"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Stop if the provider redirects to a different address.
        return None


def download_entries():
    request = Request(
        FEED_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "SMISHGUARD-Prototype/0.1",
        },
    )

    opener = build_opener(NoRedirect())

    with opener.open(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError("The feed did not return HTTP 200.")

        content_type = response.headers.get_content_type()
        if content_type != "application/json":
            raise ValueError(
                f"Expected JSON, but received {content_type}."
            )

        raw = response.read(MAX_BYTES + 1)

    if len(raw) > MAX_BYTES:
        raise ValueError("The feed exceeds the 10 MiB download limit.")

    entries = json.loads(raw)

    if not isinstance(entries, list) or not entries:
        raise ValueError("Expected a nonempty JSON array.")

    # Validate the basic structure before replacing a previous snapshot.
    # Preserve provider fields without reinterpreting scores or verdicts.
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry {index} is not a JSON object.")

        url = entry.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ValueError(f"Entry {index} has no usable URL.")

        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError(
                f"Entry {index} does not contain an absolute HTTP(S) URL."
            )

    return entries


def main():
    entries = download_entries()

    snapshot = {
        "source": "PhishHunt",
        "source_url": FEED_URL,
        # This records our download time, not when a threat was confirmed.
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
    }

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=CACHE_PATH.parent,
            prefix="phishunt_",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(snapshot, temporary_file, ensure_ascii=False)

        # Replace the previous snapshot only after writing successfully.
        temporary_path.replace(CACHE_PATH)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    print("PhishHunt feed downloaded successfully.")
    print("Downloaded entries:", len(entries))
    print("Retrieved at:", snapshot["fetched_at"])
    print("Saved to:", CACHE_PATH)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, URLError) as error:
        print(f"Feed refresh failed: {error}")
        print("Any previous saved snapshot was preserved.")
        raise SystemExit(1)
        