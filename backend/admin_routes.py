import logging
import os
import secrets
from contextlib import contextmanager
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, field_validator

from database import get_connection


logger = logging.getLogger(__name__)

bearer = HTTPBearer(
    auto_error=False,
    scheme_name="AdminToken",
)

ReviewStatus = Literal[
    "pending",
    "confirmed_smishing",
    "dismissed",
    "uncertain",
]


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    expected = os.getenv("ADMIN_API_TOKEN", "").strip()

    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Admin access has not been configured.",
        )

    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode("utf-8"),
        expected.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=401,
            detail="A valid admin token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin)],
)


@contextmanager
def database_cursor():
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SET LOCAL statement_timeout = '5s'")
                yield cursor
    except psycopg.Error as error:
        logger.error(
            "Admin database operation failed: %s",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="The database operation could not be confirmed.",
        ) from None


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: Literal[
        "dismissed",
        "uncertain",
        "confirmed_smishing",
    ]
    review_notes: str = Field(
        strict=True,
        min_length=5,
        max_length=2000,
    )
    expected_status: ReviewStatus = "pending"

    @field_validator("review_notes")
    @classmethod
    def validate_notes(cls, value):
        cleaned = value.strip()
        if len(cleaned) < 5:
            raise ValueError("Explain the review decision in at least 5 characters.")
        return cleaned


@router.get("/reports/summary")
def report_summary():
    counts = {
        "pending": 0,
        "confirmed_smishing": 0,
        "dismissed": 0,
        "uncertain": 0,
    }

    with database_cursor() as cursor:
        cursor.execute("""
            SELECT review_status, COUNT(*) AS count
            FROM public.reports
            GROUP BY review_status;
        """)

        for row in cursor.fetchall():
            counts[row["review_status"]] = row["count"]

    return {
        "total_reports": sum(counts.values()),
        "by_review_status": counts,
    }


@router.get("/reports")
def list_reports(
    review_status: ReviewStatus = "pending",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    with database_cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id,
                message_text,
                input_method,
                model_label,
                model_version,
                review_status,
                review_notes,
                created_at,
                reviewed_at
            FROM public.reports
            WHERE review_status = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s;
            """,
            (review_status, limit, offset),
        )
        reports = cursor.fetchall()

    return {
        "items": reports,
        "review_status": review_status,
        "limit": limit,
        "offset": offset,
    }


@router.patch("/reports/{report_id}/review")
def review_report(report_id: UUID, decision: ReviewDecision):
    with database_cursor() as cursor:
        cursor.execute(
            """
            UPDATE public.reports
            SET
                review_status = %s,
                review_notes = %s,
                reviewed_at = CURRENT_TIMESTAMP
            WHERE id = %s AND review_status = %s
            RETURNING
                id AS report_id,
                review_status,
                review_notes,
                reviewed_at;
            """,
            (
                decision.review_status,
                decision.review_notes,
                report_id,
                decision.expected_status,
            ),
        )
        updated = cursor.fetchone()

        if updated is None:
            cursor.execute(
                "SELECT review_status FROM public.reports WHERE id = %s",
                (report_id,),
            )
            existing = cursor.fetchone()

            if existing is None:
                raise HTTPException(
                    status_code=404,
                    detail="Report not found.",
                )

            raise HTTPException(
                status_code=409,
                detail=(
                    "The report status differs from expected_status. "
                    "Refresh the report before reviewing it again."
                ),
            )

    return updated