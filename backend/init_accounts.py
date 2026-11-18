from database import get_connection


STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS public.users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

        username VARCHAR(32) NOT NULL UNIQUE
            CHECK (
                username ~ '^[a-z0-9][a-z0-9_.-]{2,31}$'
            ),

        password_hash TEXT NOT NULL
            CHECK (char_length(password_hash) > 0),

        is_active BOOLEAN NOT NULL DEFAULT TRUE,

        created_at TIMESTAMPTZ NOT NULL
            DEFAULT CURRENT_TIMESTAMP
    );
    """,

    """
    CREATE TABLE IF NOT EXISTS public.user_sessions (
        token_hash TEXT PRIMARY KEY
            CHECK (token_hash ~ '^[0-9a-f]{64}$'),

        user_id UUID NOT NULL
            REFERENCES public.users(id)
            ON DELETE CASCADE,

        created_at TIMESTAMPTZ NOT NULL
            DEFAULT CURRENT_TIMESTAMP,

        expires_at TIMESTAMPTZ NOT NULL,

        CHECK (expires_at > created_at)
    );
    """,

    """
    CREATE INDEX IF NOT EXISTS user_sessions_user_idx
    ON public.user_sessions (user_id);
    """,

    """
    CREATE INDEX IF NOT EXISTS user_sessions_expiry_idx
    ON public.user_sessions (expires_at);
    """,

    """
    CREATE TABLE IF NOT EXISTS public.analysis_history (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

        user_id UUID NOT NULL
            REFERENCES public.users(id)
            ON DELETE CASCADE,

        message_text TEXT NOT NULL
            CHECK (
                char_length(message_text) <= 5000
                AND char_length(btrim(message_text)) > 0
            ),

        input_method TEXT NOT NULL DEFAULT 'text'
            CHECK (
                input_method IN ('text', 'screenshot')
            ),

        analysis_result JSONB NOT NULL
            CHECK (
                jsonb_typeof(analysis_result) = 'object'
                AND octet_length(analysis_result::text) <= 65536
            ),

        created_at TIMESTAMPTZ NOT NULL
            DEFAULT CURRENT_TIMESTAMP
    );
    """,

    """
    CREATE INDEX IF NOT EXISTS analysis_history_owner_created_idx
    ON public.analysis_history (
        user_id,
        created_at DESC,
        id DESC
    );
    """,
)


def main():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '15s'")

            for statement in STATEMENTS:
                cursor.execute(statement)

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'users',
                      'user_sessions',
                      'analysis_history'
                  )
                ORDER BY table_name;
                """
            )

            table_names = [row[0] for row in cursor.fetchall()]

    # Print success only after the transaction has committed.
    print("Account and history table setup completed.")

    for table_name in table_names:
        print(f"Ready: public.{table_name}")


if __name__ == "__main__":
    main()