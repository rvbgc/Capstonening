"""Evaluate SMISHGUARD on a folder of SMS screenshots.

Each screenshot is sent through the same endpoints the app uses:

    POST /ocr      -> extracted text
    POST /analyze  -> model label + PhishHunt URL check

Usage (backend running, from the backend folder):

    .\\.venv\\Scripts\\python.exe evaluate_screenshots.py "C:\\dev\\smishguard-screenshots"

Step 1 - the first run creates labels.csv in that folder, listing every
         screenshot. Fill in the expected_label column for each one:
             smishing          (also accepted: phishing, scam)
             non_smishing      (also accepted: legitimate, ham, spam,
                                ordinary_spam, not_smishing)
         Leave a row blank to include it in OCR results only.
Step 2 - run the same command again. Results are written to the same folder:
             evaluation_results.csv   one row per screenshot
             evaluation_summary.md    totals, accuracy, confusion matrix

Keep the screenshots and results OUTSIDE the Git repository: they can contain
personal information. Results reflect raw OCR text without the manual review
step the app asks users to do, so they are a stricter test than real use.
"""

import csv
import json
import mimetypes
import sys
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:8000"
IMAGE_TYPES = {".png", ".jpg", ".jpeg"}
LABELS_FILE = "labels.csv"
RESULTS_FILE = "evaluation_results.csv"
SUMMARY_FILE = "evaluation_summary.md"

LABEL_ALIASES = {
    "smishing": "smishing",
    "phishing": "smishing",
    "scam": "smishing",
    "non_smishing": "non_smishing",
    "not_smishing": "non_smishing",
    "legitimate": "non_smishing",
    "ham": "non_smishing",
    "spam": "non_smishing",
    "ordinary_spam": "non_smishing",
}


def post(path, body, content_type, timeout):
    request = Request(
        BASE_URL + path,
        data=body,
        headers={"Content-Type": content_type, "Accept": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except HTTPError as error:
        try:
            detail = json.loads(error.read() or b"null")
        except ValueError:
            detail = None
        finally:
            error.close()
        return error.code, detail


def ocr(image_path):
    boundary = "----smishguard" + uuid.uuid4().hex
    content_type = mimetypes.guess_type(image_path.name)[0] or "image/png"

    body = b"".join([
        f"--{boundary}\r\n".encode(),
        (
            'Content-Disposition: form-data; name="file"; '
            f'filename="{image_path.name}"\r\n'
        ).encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        image_path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ])

    return post(
        "/ocr",
        body,
        f"multipart/form-data; boundary={boundary}",
        timeout=60,
    )


def analyze(text):
    body = json.dumps({"text": text}).encode("utf-8")
    return post("/analyze", body, "application/json", timeout=60)


def error_detail(data):
    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, dict):
            return str(detail.get("code") or detail)
    return ""


def load_labels(folder, images):
    labels_path = folder / LABELS_FILE

    if not labels_path.exists():
        with labels_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["filename", "expected_label", "notes"])
            for image in images:
                writer.writerow([image.name, "", ""])

        print(f"Created {labels_path}")
        print(
            "Fill in expected_label (smishing / non_smishing) for each "
            "screenshot, then run this command again."
        )
        return None

    labels = {}

    with labels_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("filename") or "").strip()
            raw = (row.get("expected_label") or "").strip().lower()

            if not name:
                continue

            if raw and raw not in LABEL_ALIASES:
                raise SystemExit(
                    f"Unknown expected_label '{raw}' for {name}. "
                    "Use smishing or non_smishing."
                )

            labels[name] = (LABEL_ALIASES.get(raw, ""), raw)

    return labels


def check_server():
    try:
        with urlopen(BASE_URL + "/health", timeout=10) as response:
            data = json.loads(response.read())
    except (URLError, OSError, ValueError):
        raise SystemExit(
            f"Cannot reach the backend at {BASE_URL}. Start it first."
        )

    if not data.get("model_ready"):
        raise SystemExit("The backend is running but the model is not ready.")


def evaluate(folder):
    images = sorted(
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_TYPES
    )

    if not images:
        raise SystemExit(f"No PNG or JPEG screenshots found in {folder}")

    labels = load_labels(folder, images)
    if labels is None:
        return

    check_server()

    rows = []

    for number, image in enumerate(images, start=1):
        expected, original_label = labels.get(image.name, ("", ""))
        row = {
            "filename": image.name,
            "expected_label": expected,
            "original_label": original_label,
            "ocr_status": "",
            "ocr_characters": 0,
            "ocr_text": "",
            "predicted_label": "",
            "correct": "",
            "url_status": "",
            "error": "",
        }

        print(f"[{number}/{len(images)}] {image.name} ... ", end="", flush=True)

        if image.stat().st_size > 5 * 1024 * 1024:
            row["ocr_status"] = "skipped"
            row["error"] = "Image larger than 5 MB"
            rows.append(row)
            print("skipped (over 5 MB)")
            continue

        status, data = ocr(image)

        if status != 200 or not isinstance(data, dict) or not data.get("text"):
            row["ocr_status"] = "failed"
            row["error"] = f"OCR HTTP {status}: {error_detail(data)}".strip()
            rows.append(row)
            print(f"OCR failed ({status})")
            continue

        text = data["text"].strip()
        row["ocr_status"] = "ok"
        row["ocr_characters"] = len(text)
        row["ocr_text"] = text.replace("\r", " ").replace("\n", " ")

        status, result = analyze(text)

        if status != 200 or not isinstance(result, dict):
            row["error"] = f"Analyze HTTP {status}: {error_detail(result)}".strip()
            rows.append(row)
            print(f"analysis failed ({status})")
            continue

        row["predicted_label"] = result.get("label", "")
        threat = result.get("threat_intelligence") or {}
        row["url_status"] = threat.get("status", "") if isinstance(threat, dict) else ""

        if expected:
            row["correct"] = "yes" if row["predicted_label"] == expected else "no"

        rows.append(row)
        print(
            f"{row['predicted_label']}"
            + (f" (expected {expected})" if expected else "")
        )

    write_results(folder, rows)
    write_summary(folder, rows)


def write_results(folder, rows):
    path = folder / RESULTS_FILE

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {path}")


def percent(part, whole):
    return f"{part / whole:.1%}" if whole else "n/a"


def write_summary(folder, rows):
    total = len(rows)
    ocr_ok = [row for row in rows if row["ocr_status"] == "ok"]
    analysed = [row for row in ocr_ok if row["predicted_label"]]
    labelled = [row for row in analysed if row["expected_label"]]
    correct = [row for row in labelled if row["correct"] == "yes"]

    matrix = Counter(
        (row["expected_label"], row["predicted_label"]) for row in labelled
    )
    url_counts = Counter(row["url_status"] or "none" for row in analysed)

    tp = matrix[("smishing", "smishing")]
    fn = matrix[("smishing", "non_smishing")]
    fp = matrix[("non_smishing", "smishing")]
    tn = matrix[("non_smishing", "non_smishing")]

    precision = percent(tp, tp + fp)
    recall = percent(tp, tp + fn)

    lines = [
        "# SMISHGUARD screenshot evaluation",
        "",
        f"Run: {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "Pipeline: screenshot -> /ocr (Tesseract) -> /analyze "
        "(TF-IDF + linear SVM, PhishHunt URL check).",
        "OCR text was used as-is, without the manual correction step "
        "the app asks users to do.",
        "",
        "## Totals",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Screenshots | {total} |",
        f"| OCR produced text | {len(ocr_ok)} ({percent(len(ocr_ok), total)}) |",
        f"| Analysed by the model | {len(analysed)} |",
        f"| Analysed and labelled | {len(labelled)} |",
        f"| Correct predictions | {len(correct)} "
        f"({percent(len(correct), len(labelled))}) |",
        f"| Smishing precision | {precision} |",
        f"| Smishing recall | {recall} |",
        "",
        "## Confusion matrix (rows = expected, columns = predicted)",
        "",
        "| | non_smishing | smishing |",
        "|---|---|---|",
        f"| **non_smishing** | {tn} | {fp} |",
        f"| **smishing** | {fn} | {tp} |",
        "",
        "## PhishHunt URL-check results",
        "",
        "| Status | Count |",
        "|---|---|",
    ]

    lines += [f"| {status} | {count} |" for status, count in url_counts.most_common()]

    failures = [row for row in rows if row["error"]]
    if failures:
        lines += ["", "## Failures", "", "| Screenshot | Reason |", "|---|---|"]
        lines += [f"| {row['filename']} | {row['error']} |" for row in failures]

    lines += [
        "",
        "## Notes for interpretation",
        "",
        f"- This is a small sample ({total} screenshots). "
        "Treat percentages as indicative, not conclusive.",
        "- A PhishHunt `not_listed` result means no cached match; "
        "it does not show a link is safe.",
        "- Model output is binary (smishing / non_smishing) and uncalibrated.",
    ]

    path = folder / SUMMARY_FILE
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {path}\n")
    print("\n".join(lines[7:18]))


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)

    folder = Path(sys.argv[1]).expanduser().resolve()

    if not folder.is_dir():
        raise SystemExit(f"Folder not found: {folder}")

    repo_root = Path(__file__).resolve().parent.parent
    if repo_root in folder.parents or folder == repo_root:
        raise SystemExit(
            "Keep screenshots outside the Git repository; "
            "they may contain personal information."
        )

    evaluate(folder)


if __name__ == "__main__":
    main()
