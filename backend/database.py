import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


load_dotenv(
    Path(__file__).with_name(".env"),
    interpolate=False,
)


def get_connection():
    password = os.getenv("DB_PASSWORD")

    if not password or password == "REPLACE_WITH_APP_PASSWORD":
        raise RuntimeError(
            "Set DB_PASSWORD in backend/.env before connecting."
        )

    return psycopg.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "smishguard"),
        user=os.getenv("DB_USER", "smishguard_app"),
        password=password,
        connect_timeout=5,
        application_name="smishguard_backend",
    )


if __name__ == "__main__":
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user")
            database_name, database_user = cursor.fetchone()

    print("Database connected successfully.")
    print(f"Database: {database_name}")
    print(f"User: {database_user}")