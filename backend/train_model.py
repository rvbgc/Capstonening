import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC


DATA = Path(r"C:\dev\smishguard-data")
FILES = [
    "SMISHGUARD_Batch_A_reviewed.xlsx",
    "Reviewed SMISHGUARD_Batch_B.xlsx",
]

SEED = 42
CLASSES = ["non_smishing", "smishing"]
REQUIRED = {
    "message_id",
    "message_text",
    "language",
    "label",
    "review_status",
}

# Read both workbooks. The original files are never modified.
frames = []
source_hashes = {}

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
        raise SystemExit(f"{filename}: missing columns {sorted(missing)}")

    frame["source_workbook"] = filename
    frames.append(frame)
    source_hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()

all_rows = pd.concat(frames, ignore_index=True)

ids = all_rows["message_id"].str.strip().str.casefold()
if ids.eq("").any() or ids.duplicated().any():
    raise SystemExit("Blank or repeated message IDs found. Check the files.")

# Use normalized copies for selecting rows; preserve original annotations.
language = all_rows["language"].str.strip().str.casefold()
label = all_rows["label"].str.strip().str.casefold()
status = all_rows["review_status"].str.strip().str.casefold()

eligible = (
    language.eq("english")
    & status.eq("reviewed")
    & label.isin(["smishing", "legitimate", "ordinary_spam"])
)

data = all_rows.loc[eligible].copy()
data["reviewed_label"] = label.loc[eligible]
data = data.reset_index(drop=True)

if data.empty:
    raise SystemExit("No eligible English messages were found.")

if data["message_text"].str.strip().eq("").any():
    raise SystemExit("An eligible message has empty text.")

data["target"] = data["reviewed_label"].map({
    "smishing": "smishing",
    "legitimate": "non_smishing",
    "ordinary_spam": "non_smishing",
})

print("Included messages:", len(data))
print("Excluded messages:", len(all_rows) - len(data))
print("\nIncluded reviewed labels:")
print(data["reviewed_label"].value_counts().to_string())

# Group related templates BEFORE splitting.
# This similarity check is separate from the classifier.
parents = list(range(len(data)))


def find_root(index):
    while parents[index] != index:
        parents[index] = parents[parents[index]]
        index = parents[index]
    return index


def join_groups(left, right):
    parents[find_root(right)] = find_root(left)


# Respect existing suggested groups when available.
if "suggested_template_group" in data.columns:
    known_groups = {}
    for index, value in enumerate(data["suggested_template_group"]):
        value = value.strip()
        if value:
            if value in known_groups:
                join_groups(index, known_groups[value])
            else:
                known_groups[value] = index


def template_text(text):
    text = text.casefold()
    text = re.sub(r"(?:https?://|www\.)\S+", " URL ", text)
    text = re.sub(r"\d+", " NUMBER ", text)
    return re.sub(r"\s+", " ", text).strip()


templates = data["message_text"].map(template_text)

group_vectorizer = TfidfVectorizer(
    analyzer="char_wb",
    ngram_range=(3, 5),
)

group_features = group_vectorizer.fit_transform(templates)
similarities = (group_features @ group_features.T).toarray()

for left in range(len(data)):
    for right in range(left):
        if similarities[left, right] >= 0.90:
            join_groups(left, right)

data["split_group"] = [
    f"group_{find_root(index)}" for index in range(len(data))
]

group_counts = data.groupby("target")["split_group"].nunique()
if len(group_counts) != 2 or group_counts.min() < 5:
    raise SystemExit(
        "Too few independent groups for this split. "
        "Send the output here before continuing."
    )

# Use one predetermined fold as the held-out test set.
# The other folds form the training set: approximately 80% / 20%.
splitter = StratifiedGroupKFold(
    n_splits=5,
    shuffle=True,
    random_state=SEED,
)

train_indexes, test_indexes = next(
    splitter.split(
        data["message_text"],
        data["target"],
        groups=data["split_group"],
    )
)

train = data.iloc[train_indexes].copy()
test = data.iloc[test_indexes].copy()

if train["target"].nunique() != 2 or test["target"].nunique() != 2:
    raise SystemExit(
        "This split does not contain both classes in both sets. "
        "Send the output here before continuing."
    )

assert set(train["split_group"]).isdisjoint(set(test["split_group"]))

print("\nTraining messages:", len(train))
print("Test messages:", len(test))
print("Template groups:", data["split_group"].nunique())
print("\nTest-set reviewed labels:")
print(test["reviewed_label"].value_counts().to_string())

# The classifier's TF-IDF vocabulary is fitted ONLY on training text.
model = Pipeline([
    (
        "tfidf",
        TfidfVectorizer(
            ngram_range=(1, 2),
            sublinear_tf=True,
        ),
    ),
    (
        "svm",
        LinearSVC(
            class_weight="balanced",
            random_state=SEED,
            max_iter=10000,
        ),
    ),
])

print("\nTraining TF-IDF + SVM...")
model.fit(train["message_text"], train["target"])
predictions = model.predict(test["message_text"])

print("\nHELD-OUT TEST RESULTS")
print(classification_report(
    test["target"],
    predictions,
    labels=CLASSES,
    digits=3,
    zero_division=0,
))

matrix = confusion_matrix(
    test["target"],
    predictions,
    labels=CLASSES,
)

print("Confusion matrix: rows = actual, columns = predicted")
print(pd.DataFrame(
    matrix,
    index=CLASSES,
    columns=CLASSES,
).to_string())

test["predicted_label"] = predictions
test["correct"] = test["target"].eq(test["predicted_label"])

by_label = test.groupby("reviewed_label")["correct"].agg(
    tested="count",
    correct="sum",
)
by_label["errors"] = by_label["tested"] - by_label["correct"]

print("\nResults by original reviewed label:")
print(by_label.to_string())

if not test["reviewed_label"].eq("legitimate").any():
    print(
        "\nNo legitimate messages are in this test set. "
        "False alarms on legitimate SMS cannot be assessed."
    )

# Save a new run each time, outside the GitHub project.
run_name = datetime.now().strftime("trial_%Y%m%d_%H%M%S_%f")
output = DATA / "model_runs" / run_name
output.mkdir(parents=True, exist_ok=False)

joblib.dump(model, output / "smishguard_model.joblib")

# These private snapshots contain message text and reviewed annotations.
train.to_csv(output / "training_split.csv", index=False, encoding="utf-8-sig")
test.to_csv(output / "test_predictions.csv", index=False, encoding="utf-8-sig")

report = {
    "status": "preliminary",
    "language": "English",
    "seed": SEED,
    "sklearn_version": sklearn.__version__,
    "source_sha256": source_hashes,
    "training_messages": len(train),
    "test_messages": len(test),
    "template_similarity_threshold": 0.90,
    "class_order": CLASSES,
    "confusion_matrix": matrix.tolist(),
    "metrics": classification_report(
        test["target"],
        predictions,
        labels=CLASSES,
        output_dict=True,
        zero_division=0,
    ),
    "limitations": [
        "Uses existing reviewer labels without independent verification.",
        "Very few legitimate English messages are available.",
        "Automatic grouping may miss related campaigns.",
        "Outputs class labels, not calibrated probabilities or risk levels.",
    ],
}

(output / "evaluation.json").write_text(
    json.dumps(report, indent=2),
    encoding="utf-8",
)

print("\nSaved model and evaluation to:")
print(output)
print("\nOriginal Excel files were not changed.")
