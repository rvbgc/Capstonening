import logging
from typing import Literal

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from database import get_connection
from model_service import model_ready, predict_message


router = APIRouter(prefix="/reports", tags=["Reports"])
logger = logging.getLogger(__name__)


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(strict=True, min_length=1, max_length=5000)
    input_method: Literal["text", "screenshot"] = "text"
    consent: StrictBool

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Enter a message before submitting a report.")
        return cleaned

    @field_validator("consent")
    @classmethod
    def require_consent(cls, value):
        if not value:
            raise ValueError("Consent is required to submit a report.")
        return value


@router.post("", status_code=201)
def submit_report(submission: ReportRequest):
    prediction = None

    if model_ready():
        prediction = predict_message(submission.text)

    model_label = prediction["label"] if prediction else None
    model_version = prediction["model_version"] if prediction else None

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.reports (
                        message_text,
                        input_method,
                        model_label,
                        model_version
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, review_status, created_at;
                    """,
                    (
                        submission.text,
                        submission.input_method,
                        model_label,
                        model_version,
                    ),
                )

                report_id, review_status, created_at = cursor.fetchone()

    except psycopg.Error as error:
        logger.error(
            "Report database operation failed: %s",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=503,
            detail={
                "code": "REPORT_STORAGE_UNAVAILABLE",
                "message": (
                    "Report submission could not be confirmed. "
                    "Please try again later."
                ),
            },
        ) from None

    return {
        "report_id": str(report_id),
        "review_status": review_status,
        "created_at": created_at.isoformat(),
        "message": "Report submitted for review. It has not been verified.",
    }