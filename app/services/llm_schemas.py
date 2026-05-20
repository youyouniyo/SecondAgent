from pydantic import BaseModel, Field


class EvaluationDetailResult(BaseModel):
    """평가 내용 단위의 점수와 의견입니다."""

    criteria_detail_id: int
    score: int = Field(..., ge=0, le=100)
    weight: int = Field(..., ge=0, le=100)
    comment: str


class CriteriaEvaluationResult(BaseModel):
    """평가 항목 하나에 대한 LLM의 결과입니다."""

    criteria_item_id: int
    criteria_name: str
    score: int = Field(..., ge=0, le=100)
    grade: str
    comment: str
    details: list[EvaluationDetailResult]


class SuggestionResult(BaseModel):
    """문서에서 실제로 수정이 필요한 문구 하나에 대한 제안입니다."""

    criteria_item_id: int
    criteria_name: str
    original_text: str
    evaluation_content: str
    analysis_result: str
    recommended_text: str
    severity: str = "medium"
    document_order: int = 1


class ModelEvaluationResult(BaseModel):
    """개별 evaluator LLM이 반환해야 하는 전체 결과 형식입니다."""

    model_name: str
    evaluation_summary: str
    overall_score: int = Field(..., ge=0, le=100)
    overall_grade: str
    ai_readable_status: str
    criteria_results: list[CriteriaEvaluationResult]
    suggestions: list[SuggestionResult]


class AggregatedResult(BaseModel):
    """Aggregator LLM이 재판정 후 반환하는 결과 형식입니다."""

    final_summary: str
    overall_score: int = Field(..., ge=0, le=100)
    overall_grade: str
    ai_readable_status: str
    criteria_results: list[CriteriaEvaluationResult]
    suggestions: list[SuggestionResult]
    aggregation_reason: str
