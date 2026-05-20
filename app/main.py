from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import initialize_database
from app.schemas import (
    ConfirmResultResponse,
    EvaluationCreateRequest,
    ReviewCreateRequest,
    SuggestionActionResponse,
)
from app.services.criteria_repository import get_active_criteria
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
