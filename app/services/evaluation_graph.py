from typing import Any, TypedDict

from app.config import get_settings
from app.services.confluence_client import ConfluencePageReader
from app.services.criteria_repository import get_active_criteria
from app.services.document_parser import normalize_document
from app.services.evaluation_repository import (
    attach_result_to_job,
    merge_model_results,
    save_final_result,
    save_model_result,
    update_job,
)


class EvaluationState(TypedDict, total=False):
    """LangGraph node들이 서로 주고받는 작업 상태입니다."""

    job_id: int
    user_id: int
    confluence_url: str
    page_id: str
    document_title: str
    original_html: str
    normalized_text: str
    document_structure: dict[str, Any]
    criteria: dict[str, Any]
    model_results: list[dict[str, Any]]
    final_result: dict[str, Any]
    result_id: int
    error: str


def run_evaluation_pipeline(job_id: int, user_id: int, confluence_url: str) -> None:
    """평가 Job 하나를 끝까지 실행합니다.

    FastAPI 요청/응답은 오래 기다리면 안 되기 때문에 이 함수는 BackgroundTasks에서
    실행됩니다. 사용자는 `/progress/{job_id}` 화면에서 DB에 저장된 진행률을 봅니다.
    """

    try:
        graph = build_graph()
        graph.invoke({"job_id": job_id, "user_id": user_id, "confluence_url": confluence_url})
    except Exception as exc:
        update_job(job_id, "failed", 100, "평가 실패", str(exc))


def build_graph():
    """LangGraph 평가 흐름을 만듭니다."""

    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(EvaluationState)
    graph.add_node("fetch_confluence_page", fetch_confluence_page)
    graph.add_node("parse_document", parse_document)
    graph.add_node("load_active_criteria", load_active_criteria)
    graph.add_node("run_parallel_llm_evaluations", run_parallel_llm_evaluations)
    graph.add_node("calculate_final_scores", calculate_final_scores)
    graph.add_node("save_evaluation_result", save_evaluation_result)

    graph.add_edge(START, "fetch_confluence_page")
    graph.add_edge("fetch_confluence_page", "parse_document")
    graph.add_edge("parse_document", "load_active_criteria")
    graph.add_edge("load_active_criteria", "run_parallel_llm_evaluations")
    graph.add_edge("run_parallel_llm_evaluations", "calculate_final_scores")
    graph.add_edge("calculate_final_scores", "save_evaluation_result")
    graph.add_edge("save_evaluation_result", END)
    return graph.compile()


def fetch_confluence_page(state: EvaluationState) -> EvaluationState:
    """Confluence에서 원문 HTML을 가져옵니다."""

    update_job(state["job_id"], "fetching_confluence", 15, "Confluence 문서를 읽는 중")
    page = ConfluencePageReader().fetch_page(state["confluence_url"])
    state["page_id"] = page.page_id
    state["document_title"] = page.title
    state["original_html"] = page.html
    return state


def parse_document(state: EvaluationState) -> EvaluationState:
    """원문 HTML을 LLM 평가용 텍스트로 변환합니다."""

    update_job(state["job_id"], "parsing_document", 30, "문서 구조를 분석하는 중")
    normalized_text, structure = normalize_document(state["original_html"])
    state["normalized_text"] = normalized_text
    state["document_structure"] = structure
    return state


def load_active_criteria(state: EvaluationState) -> EvaluationState:
    """DB에서 현재 활성 평가 기준을 읽어옵니다."""

    update_job(state["job_id"], "evaluating_models", 45, "평가 기준을 불러오는 중")
    state["criteria"] = get_active_criteria()
    return state


def run_parallel_llm_evaluations(state: EvaluationState) -> EvaluationState:
    """여러 LLM 모델을 호출해 독립 평가를 수행합니다.

    실제 서비스에서는 병렬 실행으로 속도를 높일 수 있습니다. 초기 구현에서는
    흐름을 이해하기 쉽도록 모델을 순서대로 호출합니다.
    """

    settings = get_settings()
    update_job(state["job_id"], "evaluating_models", 65, "여러 LLM이 독립 평가 중")

    model_results = []
    for model_name in settings.evaluation_model_names:
        try:
            parsed = call_evaluator_model(
                model_name=model_name,
                document=state["normalized_text"],
                criteria=state["criteria"],
            )
            model_results.append({"model_name": model_name, "success": True, "parsed": parsed})
            save_model_result(
                job_id=state["job_id"],
                model_name=model_name,
                model_role="evaluator",
                success=True,
                raw_response=None,
                parsed_response=parsed,
            )
        except Exception as exc:
            model_results.append({"model_name": model_name, "success": False, "error": str(exc)})
            save_model_result(
                job_id=state["job_id"],
                model_name=model_name,
                model_role="evaluator",
                success=False,
                raw_response=None,
                parsed_response=None,
                failure_reason=str(exc),
            )

    successful_count = len([result for result in model_results if result["success"]])
    if successful_count < 2:
        raise RuntimeError("성공한 LLM 평가가 2개 미만이라 최종 결과를 만들 수 없습니다.")

    state["model_results"] = model_results
    return state


def call_evaluator_model(model_name: str, document: str, criteria: dict[str, Any]) -> dict[str, Any]:
    """LangChain으로 evaluator LLM을 호출합니다.

    OPENAI_API_KEY가 없으면 데모 결과를 반환합니다. 이 덕분에 프론트엔드와 DB 흐름은
    API 비용 없이 먼저 확인할 수 있습니다.
    """

    settings = get_settings()
    if not settings.openai_api_key and settings.allow_demo_fallback:
        return build_demo_evaluation(model_name, criteria)

    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    from app.services.llm_schemas import ModelEvaluationResult

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You evaluate Korean Confluence documents for AI readability. Return only structured data.",
            ),
            (
                "user",
                "문서:\n{document}\n\n평가 기준:\n{criteria}\n\n수정 제안은 문서 위치 순서대로 작성하세요.",
            ),
        ]
    )
    llm = ChatOpenAI(
        model=model_name,
        api_key=settings.openai_api_key,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    chain = prompt | llm.with_structured_output(ModelEvaluationResult)
    result = chain.invoke({"document": document, "criteria": criteria})
    return result.model_dump()


def build_demo_evaluation(model_name: str, criteria: dict[str, Any]) -> dict[str, Any]:
    """LLM 없이도 화면 확인이 가능한 샘플 평가 결과를 만듭니다."""

    criteria_results = []
    for index, item in enumerate(criteria["items"]):
        score = 82 - index * 4
        criteria_results.append(
            {
                "criteria_item_id": item["id"],
                "criteria_name": item["name"],
                "score": score,
                "grade": "B" if score >= 80 else "C",
                "comment": f"{item['name']} 관점에서 일부 표현은 더 구체화할 필요가 있습니다.",
                "details": [
                    {
                        "criteria_detail_id": detail["id"],
                        "score": score,
                        "weight": detail["weight"],
                        "comment": detail["evaluation_content"],
                    }
                    for detail in item["details"]
                ],
            }
        )

    return {
        "model_name": model_name,
        "evaluation_summary": "문서의 큰 흐름은 이해 가능하지만, 일부 문구가 모호해서 AI가 실행 조건과 완료 기준을 혼동할 수 있습니다.",
        "overall_score": 76,
        "overall_grade": "C",
        "ai_readable_status": "needs_improvement",
        "criteria_results": criteria_results,
        "suggestions": [
            {
                "criteria_item_id": criteria["items"][1]["id"],
                "criteria_name": criteria["items"][1]["name"],
                "original_text": "적절히 확인하고 조치한다",
                "evaluation_content": "확인 대상과 조치 기준이 모호합니다.",
                "analysis_result": "AI가 무엇을 확인해야 하는지, 어떤 조건에서 조치가 끝나는지 판단하기 어렵습니다.",
                "recommended_text": "알림 ID, 오류율, 영향 API를 확인한 뒤 심각도 기준에 따라 조치한다",
                "severity": "medium",
                "document_order": 1,
            },
            {
                "criteria_item_id": criteria["items"][3]["id"],
                "criteria_name": criteria["items"][3]["name"],
                "original_text": "필요한 경우 개선한다",
                "evaluation_content": "개선이 필요한 조건이 구체적으로 정의되어 있지 않습니다.",
                "analysis_result": "AI가 후속 작업의 시작 조건을 판단하기 어렵습니다.",
                "recommended_text": "장애 원인이 반복 가능하거나 재발 위험이 높으면 개선 과제를 등록한다",
                "severity": "low",
                "document_order": 2,
            },
        ],
    }


def calculate_final_scores(state: EvaluationState) -> EvaluationState:
    """모델별 결과를 평균/중앙값 정책에 따라 최종 결과로 합칩니다."""

    update_job(state["job_id"], "aggregating", 85, "모델 의견을 비교하고 최종 결과를 만드는 중")
    score_method = state["criteria"].get("score_method", "median")
    state["final_result"] = merge_model_results(state["model_results"], score_method)
    return state


def save_evaluation_result(state: EvaluationState) -> EvaluationState:
    """최종 결과를 DB에 저장하고 Job을 완료 처리합니다."""

    result_id = save_final_result(
        job_id=state["job_id"],
        criteria_version_id=state["criteria"]["id"],
        document_title=state["document_title"],
        confluence_url=state["confluence_url"],
        original_html=state["original_html"],
        final_result=state["final_result"],
    )
    attach_result_to_job(state["job_id"], result_id)
    state["result_id"] = result_id
    return state
