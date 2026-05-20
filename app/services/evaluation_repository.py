import sqlite3
from statistics import mean, median
from typing import Any

from app.database import db_connection, json_dumps, row_to_dict, utc_now
from app.services.document_parser import build_highlighted_html


def create_job(user_id: int, confluence_url: str) -> int:
    """평가 요청 1건을 DB에 생성합니다."""

    now = utc_now()
    with db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO evaluation_jobs(user_id, confluence_url, status, progress, current_step, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, confluence_url, "queued", 0, "평가 대기 중", now, now),
        )
        return int(cursor.lastrowid)


def update_job(job_id: int, status: str, progress: int, current_step: str, error_message: str | None = None) -> None:
    """평가중 화면이 볼 수 있도록 Job 진행 상태를 업데이트합니다."""

    with db_connection() as conn:
        conn.execute(
            """
            UPDATE evaluation_jobs
            SET status = ?, progress = ?, current_step = ?, error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, progress, current_step, error_message, utc_now(), job_id),
        )


def attach_result_to_job(job_id: int, result_id: int) -> None:
    """평가 Job과 최종 결과를 연결합니다."""

    with db_connection() as conn:
        conn.execute(
            """
            UPDATE evaluation_jobs
            SET result_id = ?, status = ?, progress = ?, current_step = ?, updated_at = ?
            WHERE id = ?
            """,
            (result_id, "completed", 100, "평가 완료", utc_now(), job_id),
        )


def get_job(job_id: int) -> dict[str, Any] | None:
    """Job 1건을 조회합니다."""

    with db_connection() as conn:
        return row_to_dict(conn.execute("SELECT * FROM evaluation_jobs WHERE id = ?", (job_id,)).fetchone())


def get_demo_user_id() -> int:
    """로그인 기능이 붙기 전까지 사용할 기본 사용자 id를 가져옵니다."""

    with db_connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE email = ?", ("demo@example.com",)).fetchone()
        if row is None:
            raise RuntimeError("기본 사용자가 없습니다.")
        return int(row["id"])


def add_points(user_id: int, point_type: str, points: int, reference_id: int) -> None:
    """포인트를 적립합니다.

    UNIQUE 제약이 있기 때문에 같은 사용자/유형/대상에 대해서는 한 번만 적립됩니다.
    예를 들어 같은 평가 결과를 여러 번 확정해도 확정 포인트는 한 번만 들어갑니다.
    """

    with db_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO points(user_id, point_type, points, reference_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, point_type, points, reference_id, utc_now()),
        )


def save_model_result(
    job_id: int,
    model_name: str,
    model_role: str,
    success: bool,
    raw_response: str | None,
    parsed_response: dict | None,
    failure_reason: str | None = None,
    evaluation_result_id: int | None = None,
) -> None:
    """LLM 모델별 평가 결과나 실패 이력을 저장합니다."""

    now = utc_now()
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO llm_model_results(
                evaluation_result_id, job_id, model_name, model_role, success,
                raw_response, parsed_response, failure_reason, started_at, ended_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evaluation_result_id,
                job_id,
                model_name,
                model_role,
                1 if success else 0,
                raw_response,
                json_dumps(parsed_response) if parsed_response else None,
                failure_reason,
                now,
                now,
            ),
        )


def save_final_result(
    job_id: int,
    criteria_version_id: int,
    document_title: str,
    confluence_url: str,
    original_html: str,
    final_result: dict[str, Any],
) -> int:
    """최종 평가 결과와 점수표, 수정 제안을 한 번에 저장합니다."""

    with db_connection() as conn:
        initial_current_html = build_highlighted_html(original_html, final_result["suggestions"])

        cursor = conn.execute(
            """
            INSERT INTO evaluation_results(
                job_id, criteria_version_id, document_title, confluence_url,
                original_html, current_html, summary, overall_score, overall_grade,
                ai_readable_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                criteria_version_id,
                document_title,
                confluence_url,
                original_html,
                initial_current_html,
                final_result["summary"],
                final_result["overall_score"],
                final_result["overall_grade"],
                final_result["ai_readable_status"],
                utc_now(),
            ),
        )
        result_id = int(cursor.lastrowid)

        for score in final_result["criteria_scores"]:
            conn.execute(
                """
                INSERT INTO criteria_scores(
                    evaluation_result_id, criteria_item_id, criteria_name,
                    final_score, grade, comment, aggregation_used
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    score["criteria_item_id"],
                    score["criteria_name"],
                    score["score"],
                    score["grade"],
                    score["comment"],
                    1 if score.get("aggregation_used") else 0,
                ),
            )

        for index, suggestion in enumerate(final_result["suggestions"], start=1):
            conn.execute(
                """
                INSERT INTO suggestions(
                    evaluation_result_id, criteria_item_id, criteria_name,
                    original_text, current_text, evaluation_content, analysis_result,
                    recommended_text, severity, document_order, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    suggestion["criteria_item_id"],
                    suggestion["criteria_name"],
                    suggestion["original_text"],
                    suggestion["original_text"],
                    suggestion["evaluation_content"],
                    suggestion["analysis_result"],
                    suggestion["recommended_text"],
                    suggestion.get("severity", "medium"),
                    suggestion.get("document_order", index),
                    "pending",
                ),
            )

        return result_id


def get_result_detail(result_id: int) -> dict[str, Any] | None:
    """결과 화면에 필요한 모든 데이터를 모아서 반환합니다."""

    with db_connection() as conn:
        result = row_to_dict(conn.execute("SELECT * FROM evaluation_results WHERE id = ?", (result_id,)).fetchone())
        if result is None:
            return None

        result["criteria_scores"] = [
            row_to_dict(row)
            for row in conn.execute(
                "SELECT * FROM criteria_scores WHERE evaluation_result_id = ? ORDER BY id ASC",
                (result_id,),
            ).fetchall()
        ]
        result["suggestions"] = [
            row_to_dict(row)
            for row in conn.execute(
                "SELECT * FROM suggestions WHERE evaluation_result_id = ? ORDER BY document_order ASC, id ASC",
                (result_id,),
            ).fetchall()
        ]
        return result


def apply_suggestion(suggestion_id: int) -> dict[str, Any]:
    """AI추천 문구를 결과 preview에 반영합니다."""

    with db_connection() as conn:
        suggestion = row_to_dict(conn.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone())
        if suggestion is None:
            raise ValueError("수정 제안을 찾을 수 없습니다.")

        result = row_to_dict(
            conn.execute(
                "SELECT * FROM evaluation_results WHERE id = ?",
                (suggestion["evaluation_result_id"],),
            ).fetchone()
        )
        if result is None:
            raise ValueError("평가 결과를 찾을 수 없습니다.")

        conn.execute(
            """
            UPDATE suggestions
            SET current_text = ?, status = ?
            WHERE id = ?
            """,
            (suggestion["recommended_text"], "applied", suggestion_id),
        )
        suggestions = _suggestions_for_result(conn, result["id"], override={suggestion_id: "applied"})
        new_html = build_highlighted_html(result["original_html"], suggestions)
        conn.execute("UPDATE evaluation_results SET current_html = ? WHERE id = ?", (new_html, result["id"]))
        conn.execute(
            """
            INSERT INTO suggestion_actions(suggestion_id, action_type, before_text, after_text, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (suggestion_id, "apply", suggestion["current_text"], suggestion["recommended_text"], utc_now()),
        )
        return {"suggestion_id": suggestion_id, "status": "applied", "current_text": suggestion["recommended_text"], "current_html": new_html}


def revert_suggestion(suggestion_id: int) -> dict[str, Any]:
    """AI추천 문구를 원래 문구로 되돌립니다."""

    with db_connection() as conn:
        suggestion = row_to_dict(conn.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone())
        if suggestion is None:
            raise ValueError("수정 제안을 찾을 수 없습니다.")

        result = row_to_dict(
            conn.execute(
                "SELECT * FROM evaluation_results WHERE id = ?",
                (suggestion["evaluation_result_id"],),
            ).fetchone()
        )
        if result is None:
            raise ValueError("평가 결과를 찾을 수 없습니다.")

        conn.execute(
            """
            UPDATE suggestions
            SET current_text = ?, status = ?
            WHERE id = ?
            """,
            (suggestion["original_text"], "pending", suggestion_id),
        )
        suggestions = _suggestions_for_result(conn, result["id"], override={suggestion_id: "pending"})
        new_html = build_highlighted_html(result["original_html"], suggestions)
        conn.execute("UPDATE evaluation_results SET current_html = ? WHERE id = ?", (new_html, result["id"]))
        conn.execute(
            """
            INSERT INTO suggestion_actions(suggestion_id, action_type, before_text, after_text, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (suggestion_id, "revert", suggestion["current_text"], suggestion["original_text"], utc_now()),
        )
        return {"suggestion_id": suggestion_id, "status": "pending", "current_text": suggestion["original_text"], "current_html": new_html}


def confirm_result(result_id: int, user_id: int) -> None:
    """평가 결과를 확정하고 포인트를 적립합니다."""

    with db_connection() as conn:
        conn.execute(
            "UPDATE evaluation_results SET confirmed_at = COALESCE(confirmed_at, ?) WHERE id = ?",
            (utc_now(), result_id),
        )
    add_points(user_id, "confirm", 2, result_id)


def _suggestions_for_result(
    conn: sqlite3.Connection,
    result_id: int,
    override: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """특정 결과의 제안 목록을 읽고, 방금 바뀐 상태를 임시로 반영합니다."""

    override = override or {}
    rows = conn.execute(
        "SELECT * FROM suggestions WHERE evaluation_result_id = ? ORDER BY document_order ASC, id ASC",
        (result_id,),
    ).fetchall()
    suggestions = []
    for row in rows:
        suggestion = row_to_dict(row)
        if suggestion["id"] in override:
            suggestion["status"] = override[suggestion["id"]]
        suggestions.append(suggestion)
    return suggestions


def save_review(result_id: int, user_id: int, rating: int, comment: str) -> None:
    """후기를 저장하고 후기 작성 포인트를 적립합니다."""

    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO reviews(evaluation_result_id, user_id, rating, comment, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (result_id, user_id, rating, comment, utc_now()),
        )
    add_points(user_id, "review", 5, result_id)


def calculate_dashboard_metrics() -> dict[str, Any]:
    """Admin Dashboard에 보여줄 운영 지표를 계산합니다."""

    with db_connection() as conn:
        total_today = conn.execute(
            "SELECT COUNT(*) AS value FROM evaluation_jobs WHERE date(created_at) = date('now')"
        ).fetchone()["value"]
        daily_users = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) AS value
            FROM evaluation_jobs
            WHERE date(created_at) = date('now')
            """
        ).fetchone()["value"]
        average_score_row = conn.execute("SELECT AVG(overall_score) AS value FROM evaluation_results").fetchone()
        suggestion_total = conn.execute("SELECT COUNT(*) AS value FROM suggestions").fetchone()["value"]
        applied_total = conn.execute(
            "SELECT COUNT(*) AS value FROM suggestions WHERE status = 'applied'"
        ).fetchone()["value"]
        aggregator_total = conn.execute(
            "SELECT COUNT(*) AS value FROM criteria_scores WHERE aggregation_used = 1"
        ).fetchone()["value"]

        apply_rate = 0 if suggestion_total == 0 else round(applied_total / suggestion_total * 100)
        average_score = average_score_row["value"] or 0
        return {
            "today_evaluations": total_today,
            "daily_evaluators": daily_users,
            "average_score": round(average_score),
            "ai_recommendation_apply_rate": apply_rate,
            "aggregator_reviews": aggregator_total,
        }


def merge_model_results(model_results: list[dict[str, Any]], score_method: str) -> dict[str, Any]:
    """여러 LLM 결과를 평균/중앙값 기준으로 하나의 최종 결과로 합칩니다."""

    successful_results = [result for result in model_results if result.get("success")]
    parsed_results = [result["parsed"] for result in successful_results]
    if not parsed_results:
        raise RuntimeError("성공한 LLM 평가 결과가 없습니다.")

    overall_scores = [result["overall_score"] for result in parsed_results]
    final_overall = median(overall_scores) if score_method == "median" else mean(overall_scores)
    representative = parsed_results[0]

    criteria_scores = []
    for criteria_index, first_score in enumerate(representative["criteria_results"]):
        model_scores = [
            result["criteria_results"][criteria_index]["score"]
            for result in parsed_results
            if len(result["criteria_results"]) > criteria_index
        ]
        final_score = median(model_scores) if score_method == "median" else mean(model_scores)
        criteria_scores.append(
            {
                "criteria_item_id": first_score["criteria_item_id"],
                "criteria_name": first_score["criteria_name"],
                "score": round(final_score),
                "grade": score_to_grade(round(final_score)),
                "comment": first_score["comment"],
                "aggregation_used": False,
            }
        )

    suggestions_by_text: dict[str, dict[str, Any]] = {}
    for result in parsed_results:
        for suggestion in result["suggestions"]:
            suggestions_by_text.setdefault(suggestion["original_text"], suggestion)

    return {
        "summary": representative["evaluation_summary"],
        "overall_score": round(final_overall),
        "overall_grade": score_to_grade(round(final_overall)),
        "ai_readable_status": representative["ai_readable_status"],
        "criteria_scores": criteria_scores,
        "suggestions": list(suggestions_by_text.values()),
    }


def score_to_grade(score: int) -> str:
    """숫자 점수를 화면용 등급으로 바꿉니다."""

    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "E"
