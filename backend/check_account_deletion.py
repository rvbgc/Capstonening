"""Checks the account-deletion endpoint against the running backend.

Run from the backend folder while the backend is running:

    .\\.venv\\Scripts\\python.exe check_account_deletion.py

It creates a temporary account, saves one history entry when the model is
ready, deletes the account, and confirms that the account, its sessions and
its history are gone. A second temporary account is used to confirm that
deleting one account does not affect another.
"""

import secrets
from uuid import UUID

from check_auth import call, expect
from database import get_connection


def make_account():
    username = "sgdel_" + secrets.token_hex(6)
    password = secrets.token_urlsafe(24)
    credentials = {"username": username, "password": password}

    status, registered = call("POST", "/auth/register", credentials)
    expect(f"Register temporary account {username}", status, 201)

    status, session = call("POST", "/auth/login", credentials)
    expect(f"Sign in as {username}", status, 200)

    return {
        "id": UUID(registered["id"]),
        "username": username,
        "password": password,
        "token": session["access_token"],
    }


def count_rows(user_id):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM public.users WHERE id = %s;",
                (user_id,),
            )
            users = cursor.fetchone()[0]

            cursor.execute(
                "SELECT count(*) FROM public.user_sessions WHERE user_id = %s;",
                (user_id,),
            )
            sessions = cursor.fetchone()[0]

            cursor.execute(
                "SELECT count(*) FROM public.analysis_history "
                "WHERE user_id = %s;",
                (user_id,),
            )
            history = cursor.fetchone()[0]

    return users, sessions, history


def save_one_analysis(account):
    status, _ = call("GET", "/health")
    expect("Health check", status, 200)

    status, result = call(
        "POST",
        "/analyze",
        {
            "text": "Account deletion check. This is a harmless test message.",
            "save_history": True,
        },
        token=account["token"],
    )

    if status == 503:
        print("SKIP: model not ready, so no history entry was saved.")
        return False

    expect("Save one analysis to history", status, 200)

    if (result or {}).get("history", {}).get("status") != "saved":
        raise RuntimeError("The analysis was not saved to history.")

    return True


def main():
    created = []

    try:
        target = make_account()
        created.append(target)

        other = make_account()
        created.append(other)

        saved = save_one_analysis(target)
        save_one_analysis(other)

        status, _ = call("POST", "/auth/delete-account", {
            "password": target["password"],
            "confirm": True,
        })
        expect("Deletion without a session rejected", status, 401)

        status, _ = call(
            "POST",
            "/auth/delete-account",
            {"password": target["password"]},
            token=target["token"],
        )
        expect("Deletion without confirmation rejected", status, 422)

        status, _ = call(
            "POST",
            "/auth/delete-account",
            {
                "password": "wrong_" + secrets.token_urlsafe(16),
                "confirm": True,
            },
            token=target["token"],
        )
        expect("Deletion with wrong password rejected", status, 403)

        status, _ = call("GET", "/auth/me", token=target["token"])
        expect("Session still valid after wrong password", status, 200)

        status, _ = call(
            "POST",
            "/auth/delete-account",
            {"password": target["password"], "confirm": True},
            token=target["token"],
        )
        expect("Account deleted", status, 204)

        status, _ = call("GET", "/auth/me", token=target["token"])
        expect("Deleted account's session rejected", status, 401)

        status, _ = call(
            "POST",
            "/auth/login",
            {"username": target["username"], "password": target["password"]},
        )
        expect("Deleted account cannot sign in", status, 401)

        if count_rows(target["id"]) != (0, 0, 0):
            raise RuntimeError(
                "Rows for the deleted account remain in the database."
            )
        print("PASS: No account, session, or history rows remain")

        other_users, other_sessions, other_history = count_rows(other["id"])

        if other_users != 1 or other_sessions < 1:
            raise RuntimeError("Deleting one account affected another account.")

        if saved and other_history < 1:
            raise RuntimeError(
                "Deleting one account removed another account's history."
            )
        print("PASS: Other account and its history are unaffected")

        status, _ = call("GET", "/auth/me", token=other["token"])
        expect("Other account still signed in", status, 200)

    finally:
        removed = 0

        with get_connection() as connection:
            with connection.cursor() as cursor:
                for account in created:
                    cursor.execute(
                        "DELETE FROM public.users "
                        "WHERE id = %s AND username = %s;",
                        (account["id"], account["username"]),
                    )
                    removed += cursor.rowcount

        if created:
            print(f"Temporary test accounts cleaned up ({removed} removed).")

    print("All account-deletion checks passed.")


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
