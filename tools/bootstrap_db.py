"""Provision service logins before applying Django-owned migrations."""

import os

import psycopg


def provision() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            "SELECT set_config('bootstrap.role_password', %s, true)",
            (os.environ["DB_ROLE_PASSWORD"],),
        )
        connection.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_reader') THEN
                    CREATE ROLE app_reader LOGIN NOSUPERUSER NOBYPASSRLS;
                END IF;
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_writer') THEN
                    CREATE ROLE app_writer LOGIN NOSUPERUSER BYPASSRLS;
                END IF;
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_django') THEN
                    CREATE ROLE app_django LOGIN NOSUPERUSER NOBYPASSRLS;
                END IF;
                EXECUTE format('ALTER ROLE app_reader PASSWORD %L',
                    current_setting('bootstrap.role_password'));
                EXECUTE format('ALTER ROLE app_writer PASSWORD %L',
                    current_setting('bootstrap.role_password'));
                EXECUTE format('ALTER ROLE app_django PASSWORD %L',
                    current_setting('bootstrap.role_password'));
            END $$;
        """)


if __name__ == "__main__":
    provision()
