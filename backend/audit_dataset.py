from pathlib import Path

import pandas as pd


DATA = Path(r"C:\dev\smishguard-data")

FILES = [
    "SMISHGUARD_Batch_A_reviewed.xlsx",
    "Reviewed SMISHGUARD_Batch_B.xlsx",
]

REQUIRED = {
    "message_id",
    "message_text",
    "language",
    "label",
    "label_reason",
    "evidence_reference",
    "review_status",
}

frames = []

for filename in FILES:
    path = DATA / filename

    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    frame = pd.read_excel(
        path,
        sheet_name="Messages",
        dtype=str,
        keep_default_na=False,
    )

    missing = REQUIRED - set(frame.columns)
    if missing:
        raise SystemExit(
            f"{filename}: missing columns: {sorted(missing)}"
        )

    print(f"{filename}: {len(frame)} rows (expected 200)")
    frame["source_workbook"] = filename
    frames.append(frame)

data = pd.concat(frames, ignore_index=True)


def normalized(column):
    return data[column].str.strip().str.casefold()


ids = normalized("message_id")
texts = normalized("message_text").str.replace(
    r"\s+", " ", regex=True
)
labels = normalized("label")
languages = normalized("language")
statuses = normalized("review_status")

print("\nTOTAL MESSAGES:", len(data), "(expected 400)")
print("UNIQUE NONEMPTY IDS:", ids[ids.ne("")].nunique())
print("BLANK IDS:", int(ids.eq("").sum()))
print(
    "ROWS WITH DUPLICATE IDS:",
    int((ids.ne("") & ids.duplicated(keep=False)).sum()),
)
print("EMPTY MESSAGES:", int(texts.eq("").sum()))
print(
    "ROWS WITH REPEATED TEXT:",
    int((texts.ne("") & texts.duplicated(keep=False)).sum()),
)

for column in ["language", "label", "review_status"]:
    print(f"\n{column.upper()} COUNTS:")
    print(
        normalized(column)
        .replace("", "(blank)")
        .value_counts()
        .to_string()
    )

allowed = {
    "language": {"english", "taglish", "filipino", "other", "uncertain"},
    "label": {"smishing", "legitimate", "ordinary_spam", "uncertain"},
    "review_status": {"pending", "reviewed"},
}

for column, choices in allowed.items():
    invalid = ~normalized(column).isin(choices)
    print(f"\nINVALID OR BLANK {column.upper()}:", int(invalid.sum()))

reviewed = statuses.eq("reviewed")
print(
    "\nREVIEWED ROWS WITHOUT A REASON:",
    int((reviewed & normalized("label_reason").eq("")).sum()),
)
print(
    "ROWS WITHOUT EVIDENCE REFERENCES:",
    int(normalized("evidence_reference").eq("").sum()),
)

print("\nLANGUAGE BY LABEL:")
print(
    pd.crosstab(
        languages.replace("", "(blank)"),
        labels.replace("", "(blank)"),
    ).to_string()
)

print("\nOriginal Excel files were not changed.")
print("These checks do not verify whether the labels are correct.")