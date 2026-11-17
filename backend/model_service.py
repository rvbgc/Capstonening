import logging
from pathlib import Path

import joblib
from fastapi import HTTPException


MODEL_PATH = Path(
    r"C:\dev\smishguard-data\model_runs"
    r"\trial_20261117_140834_470042"
    r"\smishguard_model.joblib"
)

_model = None

try:
    loaded_model = joblib.load(MODEL_PATH)

    if set(loaded_model.classes_) != {"smishing", "non_smishing"}:
        raise ValueError("The model has unexpected classification labels.")

    _model = loaded_model
except Exception:
    logging.getLogger(__name__).exception("Could not load the trained model.")


def model_ready():
    return _model is not None


def predict_message(text):
    if _model is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MODEL_NOT_READY",
                "message": "The trained model could not be loaded.",
            },
        )

    label = str(_model.predict([text])[0])

    if label == "smishing":
        message = (
            "Possible smishing detected. Avoid opening suspicious links "
            "or sharing passwords and OTPs. Verify the message through "
            "the organization's official app or contact details."
        )
    else:
        message = (
            "Smishing was not detected by this prototype. "
            "This does not confirm that the message, sender, or links "
            "are safe."
        )

    return {
        "label": label,
        "message": message,
        "assessment_status": "preliminary",
        "model_version": MODEL_PATH.parent.name,
    }