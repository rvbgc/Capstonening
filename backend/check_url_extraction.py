"""Checks link recognition and feed matching in threat_intel.py.

Runs offline (no backend, database or internet needed):

    .\\.venv\\Scripts\\python.exe check_url_extraction.py

The examples are based on the kinds of messages in the screenshot
evaluation, including links split across lines by OCR.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import threat_intel
from sync_threat_feed import FEED_URL


FOUND = [
    (
        "Bare domain",
        "Confirm your Gcash here:\nkycconfirmgcash.online\nThank you",
        ["kycconfirmgcash.online"],
    ),
    (
        "Bare domain at end of sentence",
        "Please visit to redeem your favorite gift: globe-phl2i.com",
        ["globe-phl2i.com"],
    ),
    (
        "Short link without scheme",
        "May refund din po sa unang loss.\nCheck niyo po dito:\nbit.ly/4vaqjXh",
        ["bit.ly/4vaqjXh"],
    ),
    (
        "Scheme on one line, rest on the next",
        "CLICK IF INTERESTED FOR PRICE/BUY ---> https://\ninvol.co/claak77",
        ["https://invol.co/claak77"],
    ),
    (
        "Domain split before the dot",
        "Redeem now to enjoy your rewards:https://myvips\n.makeup/vipsbdo",
        ["https://myvips.makeup/vipsbdo"],
    ),
    (
        "Path split after a hyphen",
        "please cancel the transaction here: https://bit.ly/bdo-\ncanceltransfer",
        ["https://bit.ly/bdo-canceltransfer"],
    ),
    (
        "Path split before a slash",
        "this, cancel here:\nhttps://digitalbpi.cc/cancel\n/1r5t8w3y. Do NOT share",
        ["https://digitalbpi.cc/cancel/1r5t8w3y"],
    ),
    (
        "Two links, trailing punctuation removed",
        "Visit https://bdo9.top/rewards to redeem. Or cancel at "
        "https://bit.ly/bdo-canceltransfer.",
        ["https://bdo9.top/rewards", "https://bit.ly/bdo-canceltransfer"],
    ),
    (
        "Full link and a bare link together",
        "Limited offer! bit.ly/mbtitanium T&Cs apply. https://eastwest-ew.com",
        ["https://eastwest-ew.com", "bit.ly/mbtitanium"],
    ),
]

NOT_FOUND = [
    (
        "Email address",
        "Contact the affiliate (salgadorebecaopt@gmail.com) for more details",
    ),
    (
        "Missing space after a full stop",
        "Your points expire today.Please redeem them soon.",
    ),
    ("Money and numbers", "You won Php480k! Pay P17.05 or 6,553 points."),
    ("Ordinary abbreviations", "See you at 3 p.m. e.g. tomorrow, T&Cs apply."),
    ("Repeated domain counted once", None),
]


def check(label, condition, detail=""):
    if not condition:
        raise RuntimeError(f"{label}. {detail}".strip())
    print(f"PASS: {label}")


def written(text):
    return [link for link, _ in threat_intel.extract_links(text)]


def check_extraction():
    for label, text, expected in FOUND:
        actual = written(text)
        check(f"Found: {label}", actual == expected, f"Got {actual}")

    for label, text in NOT_FOUND:
        if text is None:
            actual = written("bit.ly/abc and again bit.ly/abc")
            check(label, actual == ["bit.ly/abc"], f"Got {actual}")
            continue

        actual = written(text)
        check(f"Not a link: {label}", actual == [], f"Got {actual}")


def check_feed_matching():
    original_cache = threat_intel.CACHE_PATH

    with tempfile.TemporaryDirectory() as folder:
        cache = Path(folder) / "feed.json"
        cache.write_text(json.dumps({
            "source_url": FEED_URL,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "entries": [
                {"url": "https://globe-phl2i.com/", "verdict": "phishing"},
                {"url": "http://bit.ly/4vaqjXh", "verdict": "phishing"},
            ],
        }), encoding="utf-8")

        threat_intel.CACHE_PATH = cache

        try:
            result = threat_intel.check_message_links(
                "Redeem your gift: globe-phl2i.com"
            )
            check(
                "Bare domain matches the feed's https:// entry",
                result["status"] == "matched",
                f"Got {result['status']}",
            )
            check(
                "Result marks that https:// was added",
                result["urls"][0]["scheme_added"] is True,
            )

            result = threat_intel.check_message_links(
                "Check niyo po dito: bit.ly/4vaqjXh"
            )
            check(
                "Bare short link matches the feed's http:// entry",
                result["status"] == "matched",
                f"Got {result['status']}",
            )

            result = threat_intel.check_message_links(
                "Visit https://globe-phl2i.com.evil.example/login"
            )
            check(
                "Similar but different URL is not matched",
                result["status"] == "not_listed",
                f"Got {result['status']}",
            )

            result = threat_intel.check_message_links(
                "See you at lunch tomorrow."
            )
            check(
                "Message without links reports no_urls",
                result["status"] == "no_urls",
            )
        finally:
            threat_intel.CACHE_PATH = original_cache


def main():
    check_extraction()
    check_feed_matching()
    print("All URL-check checks passed.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"FAIL: {error}")
