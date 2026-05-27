from typing import Literal

from pydantic import BaseModel, Field


class EvaluationCreateRequest(BaseModel):
    """사용자가 평가 시작 버튼을 눌렀을 때 서버로 보내는 데이터입니다."""

    confluence_url: str = Field(..., min_length=5)


class SuggestionActionResponse(BaseModel):
    """반영하기/원복하기 API가 화면에 돌려주는 응답 형식입니다."""

    suggestion_id: int
    status: Literal["pending", "applied"]
    current_text: str
    current_html: str


class ConfirmResultResponse(BaseModel):
    """사용자가 최종 확정 버튼을 눌렀을 때의 응답 형식입니다."""

    result_id: int
    confirmed: bool
    message: str


class ReviewCreateRequest(BaseModel):
    """후기 저장 요청입니다."""

    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(..., min_length=2, max_length=1000)


class CriteriaVersionCreate(BaseModel):
    """새로운 평가 기준 버전 생성 요청입니다."""

    version_name: str = Field(..., min_length=1, max_length=100)


class CriteriaVersionUpdate(BaseModel):
    """평가 기준 버전 정보 수정 요청입니다."""

    version_name: str = Field(..., min_length=1, max_length=100)


class CriteriaItemCreateRequest(BaseModel):
    """평가항목 추가 요청입니다."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    display_order: int = Field(..., ge=1)


class CriteriaItemUpdateRequest(BaseModel):
    """평가항목 수정 요청입니다."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    display_order: int = Field(..., ge=1)


class CriteriaItemDetailCreateRequest(BaseModel):
    """평가내용 추가 요청입니다."""

    evaluation_content: str = Field(..., min_length=1, max_length=500)
    weight: int = Field(..., ge=0, le=100)


class CriteriaItemDetailUpdateRequest(BaseModel):
    """평가내용 수정 요청입니다."""

    evaluation_content: str = Field(..., min_length=1, max_length=500)
    weight: int = Field(..., ge=0, le=100)


class CriteriaItemDetailResponse(BaseModel):
    """평가내용 응답입니다."""

    id: int
    criteria_item_id: int
    evaluation_content: str
    weight: int


class CriteriaItemResponse(BaseModel):
    """평가항목 응답입니다 (평가내용 포함)."""

    id: int
    criteria_version_id: int
    name: str
    description: str
    display_order: int
    details: list[CriteriaItemDetailResponse] = Field(default_factory=list)


class CriteriaVersionResponse(BaseModel):
    """평가 기준 버전 상세 응답입니다 (항목 및 내용 포함)."""

    id: int
    version_name: str
    status: str
    is_locked: int
    created_at: str
    items: list[CriteriaItemResponse] = Field(default_factory=list)


class CriteriaVersionListItemResponse(BaseModel):
    """평가 기준 버전 목록 응답입니다."""

    id: int
    version_name: str
    status: str
    is_locked: int
    created_at: str
    item_count: int


class CriteriaVersionActivateResponse(BaseModel):
    """평가 기준 버전 활성화 응답입니다."""

    message: str
    new_active_version_id: int
    previous_active_version_id: int | None


class WeightValidationResponse(BaseModel):
    """가중치 검증 응답입니다."""

    valid: bool
    total_weight: int
    message: str

