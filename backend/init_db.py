from database import get_connection


def initialize_database():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS public.reports (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

                    message_text TEXT NOT NULL
                        CHECK (
                            char_length(message_text) <= 5000
                            AND char_length(btrim(message_text)) > 0
                        ),

                    input_method TEXT NOT NULL DEFAULT 'text'
                        CHECK (
                            input_method IN ('text', 'screenshot')
                        ),

                    model_label TEXT
                        CHECK (
                            model_label IN ('smishing', 'non_smishing')
                        ),

                    model_version TEXT,

                    review_status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (
                            review_status IN (
                                'pending',
                                'confirmed_smishing',
                                'dismissed',
                                'uncertain'
                            )
                        ),

                    review_notes TEXT,

                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

                    reviewed_at TIMESTAMPTZ
                );
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS reports_review_created_idx
                ON public.reports (review_status, created_at DESC);
            """)

    print("Reports table created or already present.")
    print("No reports were inserted.")


if __name__ == "__main__":
    initialize_database()