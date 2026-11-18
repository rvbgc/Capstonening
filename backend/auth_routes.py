import hashlib
import logging
import re
import secrets
import time
from collections import deque
from contextlib import contextmanager
from datetime import datetime
from threading import BoundedSemaphore, Lock
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)
from pwdlib import PasswordHash

from database import get_connection


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Accounts"])

user_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="UserSession",
)

password_hasher = PasswordHash.recommended()
dummy_password_hash = password_hasher.hash(secrets.token_urlsafe(32))

password_slots = BoundedSemaphore(2)

# Basic per-process limits for the local prototype.
attempts = {}
attempts_lock = Lock()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        strict=True,
        min_length=3,
        max_length=32,
        pattern=r"^[a-z0-9][a-z0-9_.-]{2,31}$",
    )
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value


class RegisterRequest(LoginRequest):
    password: SecretStr = Field(min_length=12, max_length=128)


class PublicUser(BaseModel):
    id: UUID
    username: str
    created_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: PublicUser


def public_user(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "created_at": row["created_at"],
    }


def unauthorized():
    return HTTPException(
        status_code=401,
        detail="Sign in with a valid account session.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def limit_attempts(request, action, limit):
    address = request.client.host if request.client else "unknown"
    key = (action, address)
    now = time.monotonic()
    cutoff = now - 60

    with attempts_lock:
        expired_keys = [
            existing_key
            for existing_key, timestamps in attempts.items()
            if not timestamps or timestamps[-1] <= cutoff
        ]

        for existing_key in expired_keys:
            del attempts[existing_key]

        if key not in attempts and len(attempts) >= 1000:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Try again later.",
                headers={"Retry-After": "60"},
            )

        timestamps = attempts.setdefault(key, deque())

        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()

        if len(timestamps) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Too many attempts. Wait one minute and retry.",
                headers={"Retry-After": "60"},
            )

        timestamps.append(now)


@contextmanager
def password_operation():
    if not password_slots.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Account processing is busy. Try again shortly.",
        )

    try:
        yield
    except Exception as error:
        logger.error(
            "Password operation failed: %s",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Account processing is temporarily unavailable.",
        ) from None
    finally:
        password_slots.release()


@contextmanager
def account_cursor():
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SET LOCAL statement_timeout = '5s'")
                yield cursor
    except psycopg.Error as error:
        logger.error(
            "Account database operation failed: %s",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="The account service is temporarily unavailable.",
        ) from None


def token_digest(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(user_bearer),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()

    token = credentials.credentials

    if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
        raise unauthorized()

    with account_cursor() as cursor:
        cursor.execute(
            """
            SELECT
                u.id,
                u.username,
                u.created_at,
                s.token_hash,
                s.expires_at
            FROM public.user_sessions AS s
            JOIN public.users AS u ON u.id = s.user_id
            WHERE s.token_hash = %s
              AND s.expires_at > CURRENT_TIMESTAMP
              AND u.is_active = TRUE;
            """,
            (token_digest(token),),
        )
        user = cursor.fetchone()

    if user is None:
        raise unauthorized()

    return user


@router.post(
    "/register",
    status_code=201,
    response_model=PublicUser,
)
def register(submission: RegisterRequest, request: Request):
    limit_attempts(request, "register", 10)

    with password_operation():
        hashed_password = password_hasher.hash(
            submission.password.get_secret_value()
        )

    with account_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO public.users (username, password_hash)
            VALUES (%s, %s)
            ON CONFLICT (username) DO NOTHING
            RETURNING id, username, created_at;
            """,
            (submission.username, hashed_password),
        )
        user = cursor.fetchone()

    if user is None:
        raise HTTPException(
            status_code=409,
            detail="That username is already registered.",
        )

    return public_user(user)


@router.post("/login", response_model=LoginResponse)
def login(submission: LoginRequest, request: Request):
    limit_attempts(request, "login", 20)

    with account_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, username, password_hash, is_active, created_at
            FROM public.users
            WHERE username = %s;
            """,
            (submission.username,),
        )
        user = cursor.fetchone()

    stored_hash = (
        user["password_hash"] if user is not None else dummy_password_hash
    )

    with password_operation():
        password_matches = password_hasher.verify(
            submission.password.get_secret_value(),
            stored_hash,
        )

    if user is None or not password_matches or not user["is_active"]:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = secrets.token_urlsafe(32)

    with account_cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM public.user_sessions
            WHERE user_id = %s
              AND expires_at <= CURRENT_TIMESTAMP;
            """,
            (user["id"],),
        )

        cursor.execute(
            """
            INSERT INTO public.user_sessions (
                token_hash,
                user_id,
                expires_at
            )
            VALUES (
                %s,
                %s,
                CURRENT_TIMESTAMP + INTERVAL '12 hours'
            )
            RETURNING expires_at;
            """,
            (token_digest(token), user["id"]),
        )
        session = cursor.fetchone()

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": session["expires_at"],
        "user": public_user(user),
    }


@router.get("/me", response_model=PublicUser)
def current_account(user=Depends(require_user)):
    return public_user(user)


@router.post("/logout", status_code=204)
def logout(user=Depends(require_user)):
    with account_cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM public.user_sessions
            WHERE token_hash = %s
              AND user_id = %s;
            """,
            (user["token_hash"], user["id"]),
        )

    return Response(status_code=204)