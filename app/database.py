import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings


def utc_now() -> str:
    """DB에 저장하기 쉬운 UTC 시각 문자열을 만듭니다."""

    return datetime.now(timezone.utc).isoformat()


def json_dumps(value: Any) -> str:
    """dict/list 데이터를 SQLite의 TEXT 컬럼에 저장하기 위해 JSON 문자열로 바꿉니다."""

    return json.dumps(value, ensure_ascii=False)


def json_loads(value: str | None, default: Any = None) -> Any:
    """DB에 저장된 JSON 문자열을 다시 dict/list로 바꿉니다."""

    if not value:
        return default
    return json.loads(value)


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    """SQLite 연결을 열고 닫는 공통 함수입니다.

    `with db_connection() as conn:` 형태로 쓰면 함수가 끝날 때 자동으로
    연결이 닫힙니다. 실수로 DB 연결을 계속 열어두는 문제를 줄여 줍니다.
    """

    settings = get_settings()
    db_path = settings.database_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """sqlite3.Row를 일반 dict로 바꿔 FastAPI가 JSON으로 응답하기 쉽게 합니다."""

    if row is None:
        return None
    return dict(row)


def initialize_database() -> None:
    """애플리케이션에 필요한 테이블을 생성하고 기본 데이터를 넣습니다."""

    with db_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS criteria_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_name TEXT NOT NULL,
                status TEXT NOT NULL,
                score_method TEXT NOT NULL DEFAULT 'median',
                disagreement_threshold INTEGER NOT NULL DEFAULT 20,
                is_locked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS criteria_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                criteria_version_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                display_order INTEGER NOT NULL,
                FOREIGN KEY(criteria_version_id) REFERENCES criteria_versions(id)
            );

            CREATE TABLE IF NOT EXISTS criteria_item_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                criteria_item_id INTEGER NOT NULL,
                evaluation_content TEXT NOT NULL,
                weight INTEGER NOT NULL,
                FOREIGN KEY(criteria_item_id) REFERENCES criteria_items(id)
            );

            CREATE TABLE IF NOT EXISTS evaluation_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                confluence_url TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                current_step TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                result_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS evaluation_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                criteria_version_id INTEGER NOT NULL,
                document_title TEXT NOT NULL,
                confluence_url TEXT NOT NULL,
                original_html TEXT NOT NULL,
                current_html TEXT NOT NULL,
                summary TEXT NOT NULL,
                overall_score INTEGER NOT NULL,
                overall_grade TEXT NOT NULL,
                ai_readable_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                confirmed_at TEXT,
                FOREIGN KEY(job_id) REFERENCES evaluation_jobs(id),
                FOREIGN KEY(criteria_version_id) REFERENCES criteria_versions(id)
            );

            CREATE TABLE IF NOT EXISTS llm_model_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evaluation_result_id INTEGER,
                job_id INTEGER NOT NULL,
                model_name TEXT NOT NULL,
                model_role TEXT NOT NULL,
                success INTEGER NOT NULL,
                raw_response TEXT,
                parsed_response TEXT,
                failure_reason TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                FOREIGN KEY(evaluation_result_id) REFERENCES evaluation_results(id),
                FOREIGN KEY(job_id) REFERENCES evaluation_jobs(id)
            );

            CREATE TABLE IF NOT EXISTS criteria_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evaluation_result_id INTEGER NOT NULL,
                criteria_item_id INTEGER NOT NULL,
                criteria_name TEXT NOT NULL,
                final_score INTEGER NOT NULL,
                grade TEXT NOT NULL,
                comment TEXT NOT NULL,
                aggregation_used INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(evaluation_result_id) REFERENCES evaluation_results(id)
            );

            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evaluation_result_id INTEGER NOT NULL,
                criteria_item_id INTEGER NOT NULL,
                criteria_name TEXT NOT NULL,
                original_text TEXT NOT NULL,
                current_text TEXT NOT NULL,
                evaluation_content TEXT NOT NULL,
                analysis_result TEXT NOT NULL,
                recommended_text TEXT NOT NULL,
                severity TEXT NOT NULL,
                document_order INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                FOREIGN KEY(evaluation_result_id) REFERENCES evaluation_results(id)
            );

            CREATE TABLE IF NOT EXISTS suggestion_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                suggestion_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                before_text TEXT NOT NULL,
                after_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(suggestion_id) REFERENCES suggestions(id)
            );

            CREATE TABLE IF NOT EXISTS points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                point_type TEXT NOT NULL,
                points INTEGER NOT NULL,
                reference_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, point_type, reference_id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evaluation_result_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                rating INTEGER NOT NULL,
                comment TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(evaluation_result_id) REFERENCES evaluation_results(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )
        seed_default_data(conn)


def seed_default_data(conn: sqlite3.Connection) -> None:
    """처음 실행할 때 바로 평가를 테스트할 수 있도록 기본 데이터를 넣습니다."""

    existing_user = conn.execute("SELECT id FROM users WHERE email = ?", ("demo@example.com",)).fetchone()
    if existing_user is None:
        conn.execute(
            "INSERT INTO users(email, display_name, role, created_at) VALUES (?, ?, ?, ?)",
            ("demo@example.com", "Demo User", "admin", utc_now()),
        )

    active_version = conn.execute(
        "SELECT id FROM criteria_versions WHERE status = ?",
        ("active",),
    ).fetchone()
    if active_version is not None:
        return

    cursor = conn.execute(
        """
        INSERT INTO criteria_versions(version_name, status, score_method, disagreement_threshold, is_locked, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("기본 평가 기준 v1", "active", "median", 20, 0, utc_now()),
    )
    version_id = cursor.lastrowid

    criteria = [
        ("구조 명확성", "제목, 문단, 목록이 AI가 이해하기 쉬운 구조인지 평가합니다.", 1),
        ("맥락 충분성", "배경, 조건, 대상이 충분히 설명되어 있는지 평가합니다.", 2),
        ("용어 일관성", "같은 의미를 같은 용어로 표현했는지 평가합니다.", 3),
        ("실행 가능성", "읽은 뒤 바로 실행할 수 있을 만큼 구체적인지 평가합니다.", 4),
        ("불필요한 모호성", "애매한 표현이나 해석이 갈릴 표현이 적은지 평가합니다.", 5),
    ]

    for name, description, display_order in criteria:
        item_cursor = conn.execute(
            """
            INSERT INTO criteria_items(criteria_version_id, name, description, display_order)
            VALUES (?, ?, ?, ?)
            """,
            (version_id, name, description, display_order),
        )
        item_id = item_cursor.lastrowid
        conn.executemany(
            """
            INSERT INTO criteria_item_details(criteria_item_id, evaluation_content, weight)
            VALUES (?, ?, ?)
            """,
            [
                (item_id, f"{name} 기준으로 문서가 명확하게 작성되어 있는지 확인합니다.", 60),
                (item_id, f"{name} 관점에서 AI가 오해할 수 있는 표현이 있는지 확인합니다.", 40),
            ],
        )
