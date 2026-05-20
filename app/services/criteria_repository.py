from typing import Any

from app.database import db_connection, row_to_dict


def get_active_criteria() -> dict[str, Any]:
    """현재 활성화된 평가 기준 버전을 DB에서 읽어옵니다."""

    with db_connection() as conn:
        version = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_versions WHERE status = ? ORDER BY id DESC LIMIT 1",
                ("active",),
            ).fetchone()
        )
        if version is None:
            raise RuntimeError("활성 평가 기준이 없습니다.")

        items = []
        item_rows = conn.execute(
            """
            SELECT * FROM criteria_items
            WHERE criteria_version_id = ?
            ORDER BY display_order ASC
            """,
            (version["id"],),
        ).fetchall()

        for item_row in item_rows:
            item = row_to_dict(item_row)
            detail_rows = conn.execute(
                """
                SELECT * FROM criteria_item_details
                WHERE criteria_item_id = ?
                ORDER BY id ASC
                """,
                (item["id"],),
            ).fetchall()
            item["details"] = [row_to_dict(row) for row in detail_rows]
            items.append(item)

        version["items"] = items
        return version
