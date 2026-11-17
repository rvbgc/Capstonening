from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ocr_routes import OCRUploadLimit, router as ocr_router
from model_service import model_ready, predict_message
from report_routes import router as report_router
from admin_routes import router as admin_router
from threat_intel import check_message_links


app = FastAPI(title="SMISHGUARD API")

app.include_router(report_router)
app.include_router(admin_router)

app.add_middleware(OCRUploadLimit)
app.include_router(ocr_router)

class AnalysisRequest(BaseModel):
    # Reject unexpected fields instead of silently accepting them.
    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        strict=True,
        min_length=1,
        max_length=5000,
        description="One English SMS message, up to 5,000 characters.",
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
def analyze_message(submission: AnalysisRequest):
    result = predict_message(submission.text)
    result["threat_intelligence"] = check_message_links(submission.text)
    return result