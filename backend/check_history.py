import secrets
from uuid import UUID

from check_auth import call, expect
from database import get_connection


def verify(label, condition):
    if not condition:
        raise RuntimeError(f"{label} failed.")
    print(f"PASS: {label}")


def main():
    created_accounts = []

    def create_account():
        username = "sghistory_" + secrets.token_hex(6)
        credentials = {
            "username": username,
            "password": secrets.token_urlsafe(24),
        }

        status, account = call("POST", "/auth/register", credentials)
        expect("Temporary account registration", status, 201)

        if account.get("username") != username:
            raise RuntimeError("Unexpected registration response.")

        user_id = UUID(account["id"])
        created_accounts.append((user_id, username))

        status, session = call("POST", "/auth/login", credentials)
        expect("Temporary account login", status, 200)

        return {
            "id": user_id,
            "token": session["access_token"],
        }

    def save(token, text):
        status, result = call(
            "POST",
            "/analyze",
            {
                "text": text,
                "input_method": "text",
                "save_history": True,
            },
            token=token,
        )
        expect("Analysis request", status, 200)

        verify(
            "History save confirmed",
            result.get("history", {}).get("status") == "saved",
        )

        UUID(result["history"]["id"])
        return result

    def listing(token, query=""):
        status, result = call("GET", "/history" + query, token=token)
        expect("Private history listing", status, 200)
        return result

    try:
        status, health = call("GET", "/health")
        expect("Backend health", status, 200)
        verify("Existing model is ready", health.get("model_ready") is True)

        account_a = create_account()
        account_b = create_account()

        token_a = account_a["token"]
        token_b = account_b["token"]

        status, _ = call("GET", "/history")
        expect("Anonymous history access rejected", status, 401)

        status, _ = call(
            "POST",
            "/analyze",
            {"text": "Synthetic history test.", "save_history": True},
        )
        expect("Anonymous history saving rejected", status, 401)

        status, result = call(
            "POST",
            "/analyze",
            {"text": "Synthetic analysis without saving."},
            token=token_a,
        )
        expect("Analysis without saving", status, 200)
        verify(
            "Saving is opt-in",
            result.get("history", {}).get("status") == "not_requested"
            and listing(token_a)["items"] == [],
        )

        result_a = save(
            token_a,
            "Synthetic account A test. https://example.invalid/a",
        )
        result_b = save(
            token_b,
            "Synthetic account B test. https://example.invalid/b",
        )

        id_a = result_a["history"]["id"]
        id_b = result_b["history"]["id"]

        verify(
            "Account A sees only its entry",
            {item["id"] for item in listing(token_a)["items"]} == {id_a},
        )
        verify(
            "Account B sees only its entry",
            {item["id"] for item in listing(token_b)["items"]} == {id_b},
        )

        status, detail = call("GET", f"/history/{id_a}", token=token_a)
        expect("Owner can open its entry", status, 200)

        expected_snapshot = {
            key: value
            for key, value in result_a.items()
            if key != "history"
        }
        verify(
            "Saved result preserves the analysis snapshot",
            detail["analysis_result"] == expected_snapshot,
        )

        status, _ = call("GET", f"/history/{id_b}", token=token_a)
        expect("Another account's entry cannot be read", status, 404)

        status, _ = call("DELETE", f"/history/{id_b}", token=token_a)
        expect("Another account's entry cannot be deleted", status, 404)

        status, _ = call("GET", f"/history/{id_b}", token=token_b)
        expect("Other account's entry remains available", status, 200)

        status, _ = call(
            "POST",
            "/analyze",
            {
                "text": "Synthetic forged-owner test.",
                "save_history": True,
                "user_id": str(account_b["id"]),
            },
            token=token_a,
        )
        expect("Client-supplied owner rejected", status, 422)

        status, _ = call("DELETE", "/history", token=token_a)
        expect("Clear history requires confirmation", status, 400)

        status, _ = call("GET", f"/history/{id_a}", token=token_a)
        expect("Unconfirmed clear preserved the entry", status, 200)

        status, _ = call("DELETE", f"/history/{id_a}", token=token_a)
        expect("Owner can delete its entry", status, 204)

        status, _ = call("GET", f"/history/{id_a}", token=token_a)
        expect("Deleted entry is unavailable", status, 404)

        save(token_a, "Synthetic pagination test one.")
        save(token_a, "Synthetic pagination test two.")

        page_one = listing(token_a, "?limit=1&offset=0")
        page_two = listing(token_a, "?limit=1&offset=1")

        verify(
            "Pagination returns separate entries",
            len(page_one["items"]) == 1
            and len(page_two["items"]) == 1
            and page_one["items"][0]["id"] != page_two["items"][0]["id"]
            and page_one["has_more"] is True
            and page_two["has_more"] is False,
        )

        status, cleared = call(
            "DELETE", "/history?confirm=true", token=token_a
        )
        expect("Confirmed clear", status, 200)
        verify("Clear removed the owner's two entries", cleared["deleted"] == 2)
        verify("Owner's history is empty", listing(token_a)["items"] == [])

        status, _ = call("GET", f"/history/{id_b}", token=token_b)
        expect("Clearing A did not delete B's entry", status, 200)

        status, _ = call("POST", "/auth/logout", token=token_a)
        expect("Logout", status, 204)

        status, _ = call("GET", "/history", token=token_a)
        expect("Logged-out session cannot read history", status, 401)

    finally:
        if created_accounts:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    for user_id, username in created_accounts:
                        cursor.execute(
                            """
                            DELETE FROM public.users
                            WHERE id = %s AND username = %s;
                            """,
                            (user_id, username),
                        )

                        if cursor.rowcount != 1:
                            raise RuntimeError(
                                "Temporary account cleanup was not confirmed."
                            )

            print("Temporary accounts, sessions, and history removed.")

    print("All private-history checks passed.")


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