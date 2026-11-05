from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from ocr_routes import OCRUploadLimit, router as ocr_router

app = FastAPI(title="SMISHGUARD API")
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
        "model_ready": False,
    }


@app.post("/analyze")
def analyze_message(submission: AnalysisRequest):
    # FastAPI validates the submission before this function runs.
    # Do not produce a prediction until a trained model is available.
    raise HTTPException(
        status_code=503,
        detail={
            "code": "MODEL_NOT_READY",
            "message": (
                "Your message passed input validation, "
                "but detection is not available yet."
            ),
        },
    )