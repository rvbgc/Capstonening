import json
import secrets
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID

from database import get_connection


BASE_URL = "http://127.0.0.1:8000"


def call(method, path, payload=None, token=None):
    headers = {"Accept": "application/json"}
    body = None

    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")

    if token is not None:
        headers["Authorization"] = "Bearer " + token

    request = Request(
        BASE_URL + path,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read()
            data = json.loads(raw) if raw else None
            return response.status, data
    except HTTPError as error:
        status = error.code
        error.close()
        # Do not print response bodies containing submitted credentials.
        return status, None


def expect(label, actual, expected):
    if actual != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, received HTTP {actual}."
        )

    print(f"PASS: {label}")


def main():
    username = "sgcheck_" + secrets.token_hex(6)
    password = secrets.token_urlsafe(24)
    credentials = {"username": username, "password": password}
    created_id = None

    try:
        status, registered = call(
            "POST", "/auth/register", credentials
        )
        expect("Registration", status, 201)

        if registered.get("username") != username:
            raise RuntimeError("Registration returned an unexpected username.")

        created_id = UUID(registered["id"])

        status, _ = call("POST", "/auth/register", credentials)
        expect("Duplicate username rejected", status, 409)

        status, _ = call("GET", "/auth/me")
        expect("Missing token rejected", status, 401)

        status, _ = call(
            "POST",
            "/auth/login",
            {
                "username": username,
                "password": "wrong_" + secrets.token_urlsafe(24),
            },
        )
        expect("Wrong password rejected", status, 401)

        status, session = call("POST", "/auth/login", credentials)
        expect("Login", status, 200)
        token = session["access_token"]

        status, profile = call("GET", "/auth/me", token=token)
        expect("Authenticated profile", status, 200)

        if profile["id"] != str(created_id):
            raise RuntimeError("The session returned another account's ID.")

        status, _ = call(
            "GET", "/admin/reports/summary", token=token
        )
        expect("User session cannot access admin API", status, 401)

        # Expire only this temporary account's sessions.
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE public.user_sessions
                    SET created_at =
                            CURRENT_TIMESTAMP - INTERVAL '2 hours',
                        expires_at =
                            CURRENT_TIMESTAMP - INTERVAL '1 hour'
                    WHERE user_id = %s;
                    """,
                    (created_id,),
                )

        status, _ = call("GET", "/auth/me", token=token)
        expect("Expired session rejected", status, 401)

        status, session = call("POST", "/auth/login", credentials)
        expect("New login", status, 200)
        token = session["access_token"]

        status, _ = call("POST", "/auth/logout", token=token)
        expect("Logout", status, 204)

        status, _ = call("GET", "/auth/me", token=token)
        expect("Logged-out session rejected", status, 401)

    finally:
        if created_id is not None:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM public.users
                        WHERE id = %s AND username = %s;
                        """,
                        (created_id, username),
                    )
                    removed = cursor.rowcount

            if removed != 1:
                raise RuntimeError(
                    "Temporary account cleanup could not be confirmed."
                )

            print("Temporary test account removed.")

    print("All authentication checks passed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if isinstance(error, RuntimeError):
            print(f"FAIL: {error}")
        else:
            print(
                f"FAIL: {type(error).__name__}. "
                "Check the backend terminal for details."
            )
        raise SystemExit(1)