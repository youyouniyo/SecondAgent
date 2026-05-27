from typing import Any

from app.database import db_connection, row_to_dict, utc_now


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


def get_all_criteria_versions() -> list[dict[str, Any]]:
    """모든 평가 기준 버전을 조회합니다 (상태별 정렬)."""

    with db_connection() as conn:
        versions = []
        rows = conn.execute(
            """
            SELECT id, version_name, status, is_locked, created_at
            FROM criteria_versions
            ORDER BY
                CASE status
                    WHEN 'active' THEN 0
                    WHEN 'draft' THEN 1
                    WHEN 'archived' THEN 2
                    WHEN 'locked' THEN 3
                END,
                created_at DESC
            """
        ).fetchall()

        for row in rows:
            version = row_to_dict(row)
            item_count = conn.execute(
                "SELECT COUNT(*) as count FROM criteria_items WHERE criteria_version_id = ?",
                (version["id"],),
            ).fetchone()
            version["item_count"] = item_count["count"] if item_count else 0
            versions.append(version)

        return versions


def get_criteria_version_by_id(version_id: int) -> dict[str, Any] | None:
    """버전 ID로 평가 기준 버전을 상세 조회합니다 (items, details 포함)."""

    with db_connection() as conn:
        version = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
        )
        if version is None:
            return None

        items = []
        item_rows = conn.execute(
            """
            SELECT * FROM criteria_items
            WHERE criteria_version_id = ?
            ORDER BY display_order ASC
            """,
            (version_id,),
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


def create_criteria_version(version_name: str) -> dict[str, Any]:
    """새로운 draft 상태의 평가 기준 버전을 생성합니다."""

    with db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO criteria_versions(version_name, status, score_method, disagreement_threshold, is_locked, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (version_name, "draft", "median", 20, 0, utc_now()),
        )
        version_id = cursor.lastrowid

        version = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
        )
        version["items"] = []
        return version


def update_criteria_version(version_id: int, version_name: str) -> dict[str, Any] | None:
    """평가 기준 버전 정보를 수정합니다 (draft 상태만 가능)."""

    with db_connection() as conn:
        version_data = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
        )

        if version_data is None or version_data["status"] != "draft":
            return None

        conn.execute(
            "UPDATE criteria_versions SET version_name = ? WHERE id = ?",
            (version_name, version_id),
        )

        return get_criteria_version_by_id(version_id)


def activate_criteria_version(version_id: int) -> dict[str, Any]:
    """평가 기준 버전을 활성화합니다 (기존 active는 archived로)."""

    with db_connection() as conn:
        version_data = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
        )

        if version_data is None:
            raise ValueError("버전을 찾을 수 없습니다.")

        if version_data["status"] != "draft":
            raise ValueError("draft 상태의 버전만 활성화할 수 있습니다.")

        validate_result = validate_version_before_activation(version_id)
        if not validate_result["valid"]:
            raise ValueError(f"활성화 조건 미충족: {validate_result['message']}")

        previous_active = row_to_dict(
            conn.execute(
                "SELECT id FROM criteria_versions WHERE status = ?",
                ("active",),
            ).fetchone()
        )

        if previous_active:
            conn.execute(
                "UPDATE criteria_versions SET status = ? WHERE id = ?",
                ("archived", previous_active["id"]),
            )

        conn.execute(
            "UPDATE criteria_versions SET status = ? WHERE id = ?",
            ("active", version_id),
        )

        return {
            "message": "버전이 활성화되었습니다.",
            "new_active_version_id": version_id,
            "previous_active_version_id": previous_active["id"] if previous_active else None,
        }


def duplicate_criteria_version(source_version_id: int, new_version_name: str) -> dict[str, Any] | None:
    """평가 기준 버전을 복제합니다 (전체 항목 및 내용 포함)."""

    source = get_criteria_version_by_id(source_version_id)
    if source is None:
        return None

    with db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO criteria_versions(version_name, status, score_method, disagreement_threshold, is_locked, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (new_version_name, "draft", source["score_method"], source["disagreement_threshold"], 0, utc_now()),
        )
        new_version_id = cursor.lastrowid

        for item in source.get("items", []):
            item_cursor = conn.execute(
                """
                INSERT INTO criteria_items(criteria_version_id, name, description, display_order)
                VALUES (?, ?, ?, ?)
                """,
                (new_version_id, item["name"], item["description"], item["display_order"]),
            )
            new_item_id = item_cursor.lastrowid

            for detail in item.get("details", []):
                conn.execute(
                    """
                    INSERT INTO criteria_item_details(criteria_item_id, evaluation_content, weight)
                    VALUES (?, ?, ?)
                    """,
                    (new_item_id, detail["evaluation_content"], detail["weight"]),
                )

        return get_criteria_version_by_id(new_version_id)


def archive_criteria_version(version_id: int) -> dict[str, Any] | None:
    """평가 기준 버전을 보관 처리합니다."""

    with db_connection() as conn:
        version = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
        )

        if version is None:
            return None

        if version["status"] == "active":
            raise ValueError("활성 상태인 버전은 보관할 수 없습니다. 다른 버전을 활성화한 후 시도하세요.")

        conn.execute(
            "UPDATE criteria_versions SET status = ? WHERE id = ?",
            ("archived", version_id),
        )

        return get_criteria_version_by_id(version_id)


def delete_criteria_version(version_id: int) -> bool:
    """평가 기준 버전을 삭제합니다 (draft/archived만 가능)."""

    with db_connection() as conn:
        version = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
        )

        if version is None or version["status"] not in ("draft", "archived"):
            return False

        if check_version_is_used(version_id):
            return False

        conn.execute(
            "DELETE FROM criteria_item_details WHERE criteria_item_id IN (SELECT id FROM criteria_items WHERE criteria_version_id = ?)",
            (version_id,),
        )
        conn.execute(
            "DELETE FROM criteria_items WHERE criteria_version_id = ?",
            (version_id,),
        )
        conn.execute(
            "DELETE FROM criteria_versions WHERE id = ?",
            (version_id,),
        )

        return True


def lock_criteria_version(version_id: int) -> None:
    """평가 기준 버전을 locked 상태로 변경합니다."""

    with db_connection() as conn:
        conn.execute(
            "UPDATE criteria_versions SET status = ?, is_locked = ? WHERE id = ?",
            ("locked", 1, version_id),
        )


def check_version_is_used(version_id: int) -> bool:
    """평가 기준 버전이 평가에 사용되었는지 확인합니다."""

    with db_connection() as conn:
        result = conn.execute(
            "SELECT COUNT(*) as count FROM evaluation_results WHERE criteria_version_id = ?",
            (version_id,),
        ).fetchone()
        return result["count"] > 0 if result else False


def add_criteria_item(version_id: int, name: str, description: str, display_order: int) -> dict[str, Any] | None:
    """평가항목을 추가합니다."""

    with db_connection() as conn:
        version = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
        )

        if version is None or version["status"] != "draft":
            return None

        cursor = conn.execute(
            """
            INSERT INTO criteria_items(criteria_version_id, name, description, display_order)
            VALUES (?, ?, ?, ?)
            """,
            (version_id, name, description, display_order),
        )

        item_id = cursor.lastrowid
        item = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_items WHERE id = ?",
                (item_id,),
            ).fetchone()
        )
        item["details"] = []
        return item


def update_criteria_item(item_id: int, name: str, description: str, display_order: int) -> dict[str, Any] | None:
    """평가항목을 수정합니다 (draft 버전만)."""

    with db_connection() as conn:
        item = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_items WHERE id = ?",
                (item_id,),
            ).fetchone()
        )

        if item is None:
            return None

        version = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_versions WHERE id = ?",
                (item["criteria_version_id"],),
            ).fetchone()
        )

        if version is None or version["status"] != "draft":
            return None

        conn.execute(
            """
            UPDATE criteria_items
            SET name = ?, description = ?, display_order = ?
            WHERE id = ?
            """,
            (name, description, display_order, item_id),
        )

        item = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_items WHERE id = ?",
                (item_id,),
            ).fetchone()
        )
        detail_rows = conn.execute(
            """
            SELECT * FROM criteria_item_details
            WHERE criteria_item_id = ?
            ORDER BY id ASC
            """,
            (item_id,),
        ).fetchall()
        item["details"] = [row_to_dict(row) for row in detail_rows]
        return item


def delete_criteria_item(item_id: int) -> bool:
    """평가항목을 삭제합니다 (draft 버전만)."""

    with db_connection() as conn:
        item = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_items WHERE id = ?",
                (item_id,),
            ).fetchone()
        )

        if item is None:
            return False

        version = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_versions WHERE id = ?",
                (item["criteria_version_id"],),
            ).fetchone()
        )

        if version is None or version["status"] != "draft":
            return False

        conn.execute(
            "DELETE FROM criteria_item_details WHERE criteria_item_id = ?",
            (item_id,),
        )
        conn.execute(
            "DELETE FROM criteria_items WHERE id = ?",
            (item_id,),
        )

        return True


def add_criteria_item_detail(item_id: int, content: str, weight: int) -> dict[str, Any] | None:
    """평가내용을 추가합니다."""

    with db_connection() as conn:
        item = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_items WHERE id = ?",
                (item_id,),
            ).fetchone()
        )

        if item is None:
            return None

        version = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_versions WHERE id = ?",
                (item["criteria_version_id"],),
            ).fetchone()
        )

        if version is None or version["status"] != "draft":
            return None

        cursor = conn.execute(
            """
            INSERT INTO criteria_item_details(criteria_item_id, evaluation_content, weight)
            VALUES (?, ?, ?)
            """,
            (item_id, content, weight),
        )

        detail_id = cursor.lastrowid
        return row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_item_details WHERE id = ?",
                (detail_id,),
            ).fetchone()
        )


def update_criteria_item_detail(detail_id: int, content: str, weight: int) -> dict[str, Any] | None:
    """평가내용을 수정합니다 (draft 버전만)."""

    with db_connection() as conn:
        detail = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_item_details WHERE id = ?",
                (detail_id,),
            ).fetchone()
        )

        if detail is None:
            return None

        item = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_items WHERE id = ?",
                (detail["criteria_item_id"],),
            ).fetchone()
        )

        version = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_versions WHERE id = ?",
                (item["criteria_version_id"],),
            ).fetchone()
        )

        if version is None or version["status"] != "draft":
            return None

        conn.execute(
            """
            UPDATE criteria_item_details
            SET evaluation_content = ?, weight = ?
            WHERE id = ?
            """,
            (content, weight, detail_id),
        )

        return row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_item_details WHERE id = ?",
                (detail_id,),
            ).fetchone()
        )


def delete_criteria_item_detail(detail_id: int) -> bool:
    """평가내용을 삭제합니다 (draft 버전만)."""

    with db_connection() as conn:
        detail = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_item_details WHERE id = ?",
                (detail_id,),
            ).fetchone()
        )

        if detail is None:
            return False

        item = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_items WHERE id = ?",
                (detail["criteria_item_id"],),
            ).fetchone()
        )

        version = row_to_dict(
            conn.execute(
                "SELECT * FROM criteria_versions WHERE id = ?",
                (item["criteria_version_id"],),
            ).fetchone()
        )

        if version is None or version["status"] != "draft":
            return False

        conn.execute(
            "DELETE FROM criteria_item_details WHERE id = ?",
            (detail_id,),
        )

        return True


def validate_item_weights(item_id: int) -> tuple[int, bool]:
    """항목의 평가내용 가중치 합계를 검증합니다 (합계가 100%여야 함)."""

    with db_connection() as conn:
        result = conn.execute(
            """
            SELECT COALESCE(SUM(weight), 0) as total_weight
            FROM criteria_item_details
            WHERE criteria_item_id = ?
            """,
            (item_id,),
        ).fetchone()

        total_weight = result["total_weight"] if result else 0
        is_valid = total_weight == 100

        return total_weight, is_valid


def validate_version_before_activation(version_id: int) -> dict[str, Any]:
    """버전 활성화 전 검증합니다 (최소 1개 항목 + 모든 가중치 100%)."""

    with db_connection() as conn:
        items = conn.execute(
            "SELECT id FROM criteria_items WHERE criteria_version_id = ?",
            (version_id,),
        ).fetchall()

        if not items:
            return {"valid": False, "message": "최소 1개 이상의 평가항목이 필요합니다."}

        for item in items:
            total_weight, is_valid = validate_item_weights(item["id"])
            if not is_valid:
                item_name = conn.execute(
                    "SELECT name FROM criteria_items WHERE id = ?",
                    (item["id"],),
                ).fetchone()
                return {
                    "valid": False,
                    "message": f"'{item_name['name']}' 항목의 가중치 합계가 {total_weight}%입니다. (100% 필요)",
                }

        return {"valid": True, "message": "모든 검증을 통과했습니다."}
