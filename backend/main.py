from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ocr_routes import OCRUploadLimit, router as ocr_router
from model_service import model_ready, predict_message
from report_routes import router as report_router
from admin_routes import router as admin_router
from threat_intel import check_message_links
from auth_routes import router as auth_router

from typing import Literal

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials

from auth_routes import require_user, user_bearer
from history_routes import MAX_HISTORY, router as history_router, save_analysis

app = FastAPI(title="SMISHGUARD API")
app.include_router(auth_router)
app.include_router(history_router)

app.include_router(report_router)
app.include_router(admin_router)

app.add_middleware(OCRUploadLimit)
app.include_router(ocr_router)

class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        strict=True,
        min_length=1,
        max_length=5000,
        description="One English SMS message, up to 5,000 characters.",
    )

    input_method: Literal["text", "screenshot"] = "text"

    save_history: bool = Field(
        default=False,
        strict=True,
        description=(
            "Save this analysis to the signed-in account. "
            "Only the latest 100 saved analyses are retained."
        ),
    )

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError("Enter a message containing readable text.")

        return cleaned

@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_ready": model_ready(),
    }


@app.post("/analyze")
def analyze_message(
    submission: AnalysisRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(user_bearer),
):
    # Saving requires a valid session. Ordinary analysis remains available.
    user = require_user(credentials) if submission.save_history else None

    result = predict_message(submission.text)
    result["threat_intelligence"] = check_message_links(submission.text)

    if user is None:
        result["history"] = {"status": "not_requested"}
        return result

    try:
        saved = save_analysis(
            user["id"],
            submission.text,
            submission.input_method,
            result,
        )
    except HTTPException as error:
        if error.status_code != 503:
            raise

        result["history"] = {
            "status": "unconfirmed",
            "message": (
                "Analysis completed, but saving history could not be confirmed. "
                "Check your history before retrying."
            ),
        }
    else:
        result["history"] = {
            "status": "saved",
            "id": str(saved["id"]),
            "created_at": saved["created_at"].isoformat(),
            "retention_limit": MAX_HISTORY,
        }

    return result