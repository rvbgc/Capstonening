import time
from urllib.error import URLError

from sync_threat_feed import main as refresh_feed


REFRESH_SECONDS = 60 * 60
RETRY_SECONDS = 5 * 60


def main():
    print("Automatic PhishHunt refresh started.", flush=True)

    while True:
        try:
            refresh_feed()
        except (OSError, ValueError, URLError) as error:
            print(f"Refresh failed: {error}", flush=True)
            wait_seconds = RETRY_SECONDS
        else:
            wait_seconds = REFRESH_SECONDS

        print(
            f"Next attempt in {wait_seconds // 60} minutes. "
            "Leave this terminal running.",
            flush=True,
        )
        time.sleep(wait_seconds)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nFeed updater stopped.")