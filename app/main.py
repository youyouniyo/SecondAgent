from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import db_connection, initialize_database
from app.schemas import (
    ConfirmResultResponse,
    CriteriaItemCreateRequest,
    CriteriaItemDetailCreateRequest,
    CriteriaItemDetailUpdateRequest,
    CriteriaItemUpdateRequest,
    CriteriaVersionActivateResponse,
    CriteriaVersionCreate,
    CriteriaVersionUpdate,
    EvaluationCreateRequest,
    ReviewCreateRequest,
    SuggestionActionResponse,
    WeightValidationResponse,
)
from app.services.criteria_repository import (
    add_criteria_item,
    add_criteria_item_detail,
    archive_criteria_version,
    create_criteria_version,
    delete_criteria_item,
    delete_criteria_item_detail,
    delete_criteria_version,
    duplicate_criteria_version,
    get_active_criteria,
    get_all_criteria_versions,
    get_criteria_version_by_id,
    lock_criteria_version,
    update_criteria_item,
    update_criteria_item_detail,
    update_criteria_version,
    validate_item_weights,
    activate_criteria_version,
)
from app.services.evaluation_graph import run_evaluation_pipeline
from app.services.evaluation_repository import (
    add_points,
    apply_suggestion,
    calculate_dashboard_metrics,
    confirm_result,
    create_job,
    get_demo_user_id,
    get_job,
    get_result_detail,
    revert_suggestion,
    save_review,
)


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Confluence AI Readability Agent")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def on_startup() -> None:
    """서버가 시작될 때 DB 테이블과 기본 데이터를 준비합니다."""

    initialize_database()


def page_response(file_name: str) -> FileResponse:
    """정적 HTML 파일을 응답으로 돌려주는 작은 helper입니다."""

    return FileResponse(STATIC_DIR / file_name)


@app.get("/")
def main_page() -> FileResponse:
    return page_response("index.html")


@app.get("/progress/{job_id}")
def progress_page(job_id: int) -> FileResponse:
    return page_response("progress.html")


@app.get("/result/{result_id}")
def result_page(result_id: int) -> FileResponse:
    return page_response("result.html")


@app.get("/admin")
def admin_page() -> FileResponse:
    return page_response("admin.html")


@app.get("/admin/criteria")
def admin_criteria_page() -> FileResponse:
    return page_response("criteria.html")


@app.get("/admin/criteria-manage")
def admin_criteria_manage_page() -> FileResponse:
    return page_response("criteria-manage.html")


@app.post("/api/evaluations")
def start_evaluation(request: EvaluationCreateRequest, background_tasks: BackgroundTasks) -> dict:
    """평가 Job을 만들고 백그라운드에서 LangGraph 평가를 시작합니다."""

    user_id = get_demo_user_id()
    job_id = create_job(user_id, request.confluence_url)
    add_points(user_id, "request", 1, job_id)
    background_tasks.add_task(run_evaluation_pipeline, job_id, user_id, request.confluence_url)
    return {"job_id": job_id, "progress_url": f"/progress/{job_id}"}


@app.get("/api/evaluations/{job_id}")
def read_job(job_id: int) -> dict:
    """평가중 화면에서 주기적으로 호출하는 Job 상태 API입니다."""

    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="평가 Job을 찾을 수 없습니다.")
    return job


@app.get("/api/results/{result_id}")
def read_result(result_id: int) -> dict:
    """최종 결과 화면에 필요한 데이터를 반환합니다."""

    result = get_result_detail(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="평가 결과를 찾을 수 없습니다.")
    return result


@app.post("/api/suggestions/{suggestion_id}/apply", response_model=SuggestionActionResponse)
def apply_suggestion_api(suggestion_id: int) -> dict:
    """오른쪽 패널의 `반영하기` 버튼 API입니다."""

    return apply_suggestion(suggestion_id)


@app.post("/api/suggestions/{suggestion_id}/revert", response_model=SuggestionActionResponse)
def revert_suggestion_api(suggestion_id: int) -> dict:
    """오른쪽 패널의 `원복하기` 버튼 API입니다."""

    return revert_suggestion(suggestion_id)


@app.post("/api/results/{result_id}/confirm", response_model=ConfirmResultResponse)
def confirm_result_api(result_id: int) -> ConfirmResultResponse:
    """결과 확정 버튼 API입니다."""

    user_id = get_demo_user_id()
    confirm_result(result_id, user_id)
    return ConfirmResultResponse(
        result_id=result_id,
        confirmed=True,
        message="수정 된 페이지는 컨플런스에 직접 반영이 불가하여 본문을 Copy하여 직접 반영이 필요 합니다.",
    )


@app.post("/api/results/{result_id}/reviews")
def create_review_api(result_id: int, request: ReviewCreateRequest) -> dict:
    """후기 저장 API입니다."""

    user_id = get_demo_user_id()
    save_review(result_id, user_id, request.rating, request.comment)
    return {"saved": True}


@app.get("/api/admin/dashboard")
def admin_dashboard_api() -> dict:
    """Admin Dashboard 지표 API입니다."""

    return calculate_dashboard_metrics()


@app.get("/api/admin/criteria/active")
def active_criteria_api() -> dict:
    """현재 활성 평가 기준을 조회하는 API입니다."""

    return get_active_criteria()


def verify_admin_role() -> None:
    """Admin 권한을 검증합니다."""

    user_id = get_demo_user_id()
    with db_connection() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None or user["role"] != "admin":
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")


@app.get("/api/admin/criteria/versions")
def list_criteria_versions() -> list:
    """모든 평가 기준 버전 목록을 조회합니다."""

    verify_admin_role()
    return get_all_criteria_versions()


@app.post("/api/admin/criteria/versions")
def create_criteria_version_api(request: CriteriaVersionCreate) -> dict:
    """새로운 draft 상태의 평가 기준 버전을 생성합니다."""

    verify_admin_role()
    return create_criteria_version(request.version_name)


@app.get("/api/admin/criteria/versions/{version_id}")
def get_criteria_version_api(version_id: int) -> dict:
    """평가 기준 버전을 상세 조회합니다 (항목 및 내용 포함)."""

    verify_admin_role()
    result = get_criteria_version_by_id(version_id)
    if result is None:
        raise HTTPException(status_code=404, detail="기준 버전을 찾을 수 없습니다.")
    return result


@app.put("/api/admin/criteria/versions/{version_id}")
def update_criteria_version_api(version_id: int, request: CriteriaVersionUpdate) -> dict:
    """평가 기준 버전 정보를 수정합니다 (draft 상태만 가능)."""

    verify_admin_role()
    result = update_criteria_version(version_id, request.version_name)
    if result is None:
        raise HTTPException(status_code=400, detail="draft 상태인 버전만 수정 가능합니다.")
    return result


@app.post("/api/admin/criteria/versions/{version_id}/activate")
def activate_version_api(version_id: int) -> CriteriaVersionActivateResponse:
    """평가 기준 버전을 활성화합니다 (기존 active는 archived로)."""

    verify_admin_role()
    try:
        return activate_criteria_version(version_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/admin/criteria/versions/{version_id}/duplicate")
def duplicate_version_api(version_id: int, request: CriteriaVersionCreate) -> dict:
    """평가 기준 버전을 복제합니다 (전체 항목 및 내용 포함)."""

    verify_admin_role()
    result = duplicate_criteria_version(version_id, request.version_name)
    if result is None:
        raise HTTPException(status_code=400, detail="버전을 복제할 수 없습니다.")
    return result


@app.post("/api/admin/criteria/versions/{version_id}/archive")
def archive_version_api(version_id: int) -> dict:
    """평가 기준 버전을 보관 처리합니다."""

    verify_admin_role()
    try:
        result = archive_criteria_version(version_id)
        if result is None:
            raise HTTPException(status_code=400, detail="버전을 보관할 수 없습니다.")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/admin/criteria/versions/{version_id}")
def delete_version_api(version_id: int) -> dict:
    """평가 기준 버전을 삭제합니다 (draft/archived만 가능)."""

    verify_admin_role()
    success = delete_criteria_version(version_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="draft/archived 상태인 버전만 삭제 가능합니다.",
        )
    return {"deleted": True, "version_id": version_id}


@app.post("/api/admin/criteria/versions/{version_id}/items")
def add_criteria_item_api(version_id: int, request: CriteriaItemCreateRequest) -> dict:
    """평가항목을 추가합니다."""

    verify_admin_role()
    result = add_criteria_item(version_id, request.name, request.description, request.display_order)
    if result is None:
        raise HTTPException(status_code=400, detail="평가항목을 추가할 수 없습니다.")
    return result


@app.put("/api/admin/criteria/items/{item_id}")
def update_criteria_item_api(item_id: int, request: CriteriaItemUpdateRequest) -> dict:
    """평가항목을 수정합니다 (draft 버전만)."""

    verify_admin_role()
    result = update_criteria_item(item_id, request.name, request.description, request.display_order)
    if result is None:
        raise HTTPException(status_code=400, detail="draft 상태인 버전의 항목만 수정 가능합니다.")
    return result


@app.delete("/api/admin/criteria/items/{item_id}")
def delete_criteria_item_api(item_id: int) -> dict:
    """평가항목을 삭제합니다 (draft 버전만)."""

    verify_admin_role()
    success = delete_criteria_item(item_id)
    if not success:
        raise HTTPException(status_code=400, detail="draft 상태인 버전의 항목만 삭제 가능합니다.")
    return {"deleted": True, "item_id": item_id}


@app.post("/api/admin/criteria/items/{item_id}/details")
def add_criteria_detail_api(item_id: int, request: CriteriaItemDetailCreateRequest) -> dict:
    """평가내용을 추가합니다."""

    verify_admin_role()
    result = add_criteria_item_detail(item_id, request.evaluation_content, request.weight)
    if result is None:
        raise HTTPException(status_code=400, detail="평가내용을 추가할 수 없습니다.")
    return result


@app.put("/api/admin/criteria/items/details/{detail_id}")
def update_criteria_detail_api(detail_id: int, request: CriteriaItemDetailUpdateRequest) -> dict:
    """평가내용을 수정합니다 (draft 버전만)."""

    verify_admin_role()
    result = update_criteria_item_detail(detail_id, request.evaluation_content, request.weight)
    if result is None:
        raise HTTPException(status_code=400, detail="draft 상태인 버전의 내용만 수정 가능합니다.")
    return result


@app.delete("/api/admin/criteria/items/details/{detail_id}")
def delete_criteria_detail_api(detail_id: int) -> dict:
    """평가내용을 삭제합니다 (draft 버전만)."""

    verify_admin_role()
    success = delete_criteria_item_detail(detail_id)
    if not success:
        raise HTTPException(status_code=400, detail="draft 상태인 버전의 내용만 삭제 가능합니다.")
    return {"deleted": True, "detail_id": detail_id}


@app.get("/api/admin/criteria/items/{item_id}/weights-valid")
def validate_item_weights_api(item_id: int) -> WeightValidationResponse:
    """항목의 가중치 합계를 검증합니다."""

    verify_admin_role()
    total_weight, is_valid = validate_item_weights(item_id)
    return WeightValidationResponse(
        valid=is_valid,
        total_weight=total_weight,
        message="가중치 합계가 100%입니다." if is_valid else f"가중치 합계가 {total_weight}%입니다. (100% 필요)",
    )
