import logging
from contextlib import contextmanager
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from auth_routes import require_user
from database import get_connection


logger = logging.getLogger(__name__)
MAX_HISTORY = 100


def prevent_caching(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/history",
    tags=["History"],
    dependencies=[
        Depends(require_user),
        Depends(prevent_caching),
    ],
)


@contextmanager
def history_cursor():
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SET LOCAL statement_timeout = '5s'")
                cursor.execute("SET LOCAL lock_timeout = '3s'")
                yield cursor
    except psycopg.Error as error:
        logger.error(
            "History database operation failed: %s",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="The history operation could not be confirmed.",
        ) from None


def save_analysis(user_id, text, input_method, result):
    with history_cursor() as cursor:
        # Serialize saves for this account, including retention cleanup.
        cursor.execute(
            """
            SELECT id
            FROM public.users
            WHERE id = %s AND is_active = TRUE
            FOR UPDATE;
            """,
            (user_id,),
        )

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=401,
                detail="Sign in with an active account.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        cursor.execute(
            """
            INSERT INTO public.analysis_history (
                user_id,
                message_text,
                input_method,
                analysis_result
            )
            VALUES (%s, %s, %s, %s)
            RETURNING id, created_at;
            """,
            (user_id, text, input_method, Jsonb(result)),
        )
        saved = cursor.fetchone()

        cursor.execute(
            """
            DELETE FROM public.analysis_history
            WHERE user_id = %s
              AND id IN (
                  SELECT id
                  FROM public.analysis_history
                  WHERE user_id = %s
                  ORDER BY created_at DESC, id DESC
                  OFFSET %s
              );
            """,
            (user_id, user_id, MAX_HISTORY),
        )

    return saved


@router.get("")
def list_history(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=MAX_HISTORY),
    user=Depends(require_user),
):
    with history_cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id,
                left(message_text, 160) AS message_preview,
                input_method,
                analysis_result ->> 'label' AS label,
                analysis_result ->> 'model_version' AS model_version,
                analysis_result #>> '{threat_intelligence,status}'
                    AS url_status,
                created_at
            FROM public.analysis_history
            WHERE user_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s;
            """,
            (user["id"], limit + 1, offset),
        )
        rows = cursor.fetchall()

    return {
        "items": rows[:limit],
        "has_more": len(rows) > limit,
        "limit": limit,
        "offset": offset,
        "retention_limit": MAX_HISTORY,
    }


@router.get("/{history_id}")
def get_history_entry(
    history_id: UUID,
    user=Depends(require_user),
):
    with history_cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id,
                message_text,
                input_method,
                analysis_result,
                created_at
            FROM public.analysis_history
            WHERE id = %s AND user_id = %s;
            """,
            (history_id, user["id"]),
        )
        item = cursor.fetchone()

    if item is None:
        raise HTTPException(status_code=404, detail="History entry not found.")

    return item


@router.delete("/{history_id}", status_code=204)
def delete_history_entry(
    history_id: UUID,
    user=Depends(require_user),
):
    with history_cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM public.analysis_history
            WHERE id = %s AND user_id = %s
            RETURNING id;
            """,
            (history_id, user["id"]),
        )
        deleted = cursor.fetchone()

    if deleted is None:
        raise HTTPException(status_code=404, detail="History entry not found.")

    return Response(status_code=204)


@router.delete("")
def clear_history(
    confirm: bool = Query(False),
    user=Depends(require_user),
):
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Explicit confirmation is required to clear history.",
        )

    with history_cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM public.analysis_history
            WHERE user_id = %s;
            """,
            (user["id"],),
        )
        deleted_count = cursor.rowcount

    return {"deleted": deleted_count}