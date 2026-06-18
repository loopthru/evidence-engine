import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from uuid import UUID

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class DatabaseConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReviewRecord:
    id: UUID
    session_uid: UUID
    status: str


@dataclass(frozen=True)
class AgentStatusRecord:
    agent: str
    status: str


@dataclass(frozen=True)
class ReviewStatusRecord:
    id: UUID
    session_uid: UUID
    status: str
    summarizer_output: Any | None
    agents: list[AgentStatusRecord]


def database_url_from_env() -> str:
    settings = dotenv_values(".env")
    database_url = _setting("DATABASE_URL", settings)
    if database_url:
        return database_url

    host = _setting("HOST", settings) or _setting("PGHOST", settings)
    port = _setting("PORT", settings) or _setting("PGPORT", settings) or "5432"
    database = _setting("DATABASE", settings) or _setting("PGDATABASE", settings)
    user = _setting("DB_USER", settings) or _setting("PGUSER", settings)
    password = _setting("DB_PASSWORD", settings) or _setting("PGPASSWORD", settings)

    if not all((host, database, user, password)):
        raise DatabaseConfigurationError(
            "Database configuration requires DATABASE_URL or "
            "HOST, DATABASE, DB_USER, and DB_PASSWORD."
        )

    return (
        f"postgresql://{quote(user)}:{quote(password)}@"
        f"{host}:{port}/{quote(database, safe='')}"
    )


def _setting(name: str, dotenv_settings: dict[str, str | None]) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    dotenv_value = dotenv_settings.get(name)
    return dotenv_value if dotenv_value else None


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url_from_env(), row_factory=dict_row)


class ReviewRepository:
    def __init__(
        self,
        connection_factory: Callable[[], Any] = connect,
    ):
        self._connection_factory = connection_factory

    def insert_review(
        self,
        *,
        session_uid: UUID,
        evidence: dict[str, Any],
    ) -> ReviewRecord:
        sql = """
            INSERT INTO review (session_uid, evidence)
            VALUES (%(session_uid)s, %(evidence)s)
            ON CONFLICT (session_uid)
            DO UPDATE SET
                evidence = EXCLUDED.evidence,
                summarizer_output = NULL,
                band_chat_id = NULL,
                status = 'evidence_saved',
                updated_at = now()
            RETURNING id, session_uid, status
        """

        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    {
                        "session_uid": session_uid,
                        "evidence": Jsonb(evidence),
                    },
                )
                row = cursor.fetchone()
            connection.commit()

        return ReviewRecord(
            id=row["id"],
            session_uid=row["session_uid"],
            status=row["status"],
        )

    def get_status_by_session_uid(self, session_uid: UUID) -> ReviewStatusRecord | None:
        review_sql = """
            SELECT id, session_uid, status, summarizer_output
            FROM review
            WHERE session_uid = %(session_uid)s
        """
        agents_sql = """
            SELECT agent.display_name AS agent, review_status.status
            FROM review_status
            JOIN agent ON agent.id = review_status.agent_id
            WHERE review_status.review_id = %(review_id)s
            ORDER BY agent.display_name
        """

        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(review_sql, {"session_uid": session_uid})
                row = cursor.fetchone()
                if row is None:
                    return None

                agent_rows = []
                if row["status"] == "agents_running":
                    cursor.execute(agents_sql, {"review_id": row["id"]})
                    agent_rows = cursor.fetchall()

        return ReviewStatusRecord(
            id=row["id"],
            session_uid=row["session_uid"],
            status=row["status"],
            summarizer_output=row["summarizer_output"],
            agents=[
                AgentStatusRecord(agent=agent_row["agent"], status=agent_row["status"])
                for agent_row in agent_rows
            ],
        )
