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
