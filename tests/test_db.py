from uuid import UUID

import pytest
from psycopg.types.json import Jsonb

from evidence_engine.db import (
    AgentStatusRecord,
    DatabaseConfigurationError,
    ReviewRecord,
    ReviewRepository,
    ReviewStatusRecord,
    database_url_from_env,
)


class FakeCursor:
    def __init__(self, returned_row=None, returned_rows=None, raise_on_execute=None):
        self.returned_row = returned_row
        self.returned_rows = returned_rows
        self.raise_on_execute = raise_on_execute
        self.sql = None
        self.params = None
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params
        self.executions.append(
            {
                "sql": sql,
                "params": params,
            }
        )
        if self.raise_on_execute is not None:
            raise self.raise_on_execute

    def fetchone(self):
        return self.returned_row

    def fetchall(self):
        return self.returned_rows


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True


def clear_database_env(monkeypatch):
    for name in (
        "DATABASE_URL",
        "HOST",
        "PORT",
        "DATABASE",
        "DB_USER",
        "DB_PASSWORD",
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)


def test_database_url_from_env_reads_database_url(monkeypatch):
    clear_database_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/evidence")

    assert database_url_from_env() == "postgresql://user:pass@localhost:5432/evidence"


def test_database_url_from_env_builds_from_dotenv(monkeypatch):
    clear_database_env(monkeypatch)
    monkeypatch.setattr(
        "evidence_engine.db.dotenv_values",
        lambda _: {
            "HOST": "db.example.com",
            "PORT": "6543",
            "DATABASE": "evidence",
            "DB_USER": "reviewer@example.com",
            "DB_PASSWORD": "p@ss word",
        },
        raising=False,
    )

    assert (
        database_url_from_env()
        == "postgresql://reviewer%40example.com:p%40ss%20word@db.example.com:6543/evidence"
    )


def test_database_url_from_env_uses_process_env_before_dotenv(monkeypatch):
    clear_database_env(monkeypatch)
    monkeypatch.setenv("HOST", "env-db.example.com")
    monkeypatch.setattr(
        "evidence_engine.db.dotenv_values",
        lambda _: {
            "HOST": "file-db.example.com",
            "DATABASE": "evidence",
            "DB_USER": "reviewer",
            "DB_PASSWORD": "secret",
        },
        raising=False,
    )

    assert database_url_from_env() == "postgresql://reviewer:secret@env-db.example.com:5432/evidence"


def test_database_url_from_env_reports_missing_dotenv_settings(monkeypatch):
    clear_database_env(monkeypatch)
    monkeypatch.setattr(
        "evidence_engine.db.dotenv_values",
        lambda _: {
            "HOST": "db.example.com",
            "DATABASE": "evidence",
        },
        raising=False,
    )

    with pytest.raises(DatabaseConfigurationError) as exc_info:
        database_url_from_env()

    assert str(exc_info.value) == (
        "Database configuration requires DATABASE_URL or HOST, DATABASE, DB_USER, and DB_PASSWORD."
    )


def test_insert_review_persists_evidence_and_returns_record():
    session_uid = UUID("11111111-1111-1111-1111-111111111111")
    review_id = UUID("22222222-2222-2222-2222-222222222222")
    cursor = FakeCursor(
        returned_row={
            "id": review_id,
            "session_uid": session_uid,
            "status": "evidence_saved",
        }
    )
    connection = FakeConnection(cursor)
    repository = ReviewRepository(lambda: connection)

    record = repository.insert_review(
        session_uid=session_uid,
        evidence={"summary": {"resources_total": 0}},
    )

    assert record == ReviewRecord(
        id=review_id,
        session_uid=session_uid,
        status="evidence_saved",
    )
    assert "INSERT INTO review" in cursor.sql
    assert "INSERT INTO review (session_uid, evidence)" in cursor.sql
    assert cursor.params["session_uid"] == session_uid
    assert cursor.params["evidence"].obj == {"summary": {"resources_total": 0}}
    assert isinstance(cursor.params["evidence"], Jsonb)
    assert connection.committed is True


def test_insert_review_resets_existing_session_on_conflict():
    session_uid = UUID("11111111-1111-1111-1111-111111111111")
    review_id = UUID("22222222-2222-2222-2222-222222222222")
    cursor = FakeCursor(
        returned_row={
            "id": review_id,
            "session_uid": session_uid,
            "status": "evidence_saved",
        }
    )
    connection = FakeConnection(cursor)
    repository = ReviewRepository(lambda: connection)

    record = repository.insert_review(session_uid=session_uid, evidence={"summary": {}})

    assert record.status == "evidence_saved"
    assert "ON CONFLICT (session_uid)" in cursor.sql
    assert "evidence = EXCLUDED.evidence" in cursor.sql
    assert "summarizer_output = NULL" in cursor.sql
    assert "band_chat_id = NULL" in cursor.sql
    assert "status = 'evidence_saved'" in cursor.sql


def test_get_status_by_session_uid_fetches_review_by_session_uid():
    session_uid = UUID("11111111-1111-1111-1111-111111111111")
    review_id = UUID("22222222-2222-2222-2222-222222222222")
    cursor = FakeCursor(
        returned_row={
            "id": review_id,
            "session_uid": session_uid,
            "status": "evidence_saved",
            "summarizer_output": None,
        },
        returned_rows=[],
    )
    connection = FakeConnection(cursor)
    repository = ReviewRepository(lambda: connection)

    record = repository.get_status_by_session_uid(session_uid)

    assert record == ReviewStatusRecord(
        id=review_id,
        session_uid=session_uid,
        status="evidence_saved",
        summarizer_output=None,
        agents=[],
    )
    assert "FROM review" in cursor.executions[0]["sql"]
    assert "WHERE session_uid = %(session_uid)s" in cursor.executions[0]["sql"]
    assert cursor.executions[0]["params"] == {"session_uid": session_uid}


def test_get_status_by_session_uid_returns_none_when_review_does_not_exist():
    session_uid = UUID("11111111-1111-1111-1111-111111111111")
    cursor = FakeCursor(returned_row=None, returned_rows=[])
    connection = FakeConnection(cursor)
    repository = ReviewRepository(lambda: connection)

    record = repository.get_status_by_session_uid(session_uid)

    assert record is None
    assert len(cursor.executions) == 1
    assert "FROM review" in cursor.executions[0]["sql"]
    assert cursor.executions[0]["params"] == {"session_uid": session_uid}


def test_get_status_by_session_uid_fetches_agent_statuses_ordered_by_display_name():
    session_uid = UUID("11111111-1111-1111-1111-111111111111")
    review_id = UUID("22222222-2222-2222-2222-222222222222")
    cursor = FakeCursor(
        returned_row={
            "id": review_id,
            "session_uid": session_uid,
            "status": "agents_running",
            "summarizer_output": None,
        },
        returned_rows=[
            {"agent": "Policy", "status": "running"},
            {"agent": "Security", "status": "queued"},
        ],
    )
    connection = FakeConnection(cursor)
    repository = ReviewRepository(lambda: connection)

    record = repository.get_status_by_session_uid(session_uid)

    assert record.agents == [
        AgentStatusRecord(agent="Policy", status="running"),
        AgentStatusRecord(agent="Security", status="queued"),
    ]
    assert "FROM review_status" in cursor.executions[1]["sql"]
    assert "JOIN agent ON agent.id = review_status.agent_id" in cursor.executions[1]["sql"]
    assert "WHERE review_status.review_id = %(review_id)s" in cursor.executions[1]["sql"]
    assert "ORDER BY agent.display_name" in cursor.executions[1]["sql"]
    assert cursor.executions[1]["params"] == {"review_id": review_id}
