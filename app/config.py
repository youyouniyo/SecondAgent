from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수를 Python 코드에서 안전하게 읽기 위한 설정 클래스입니다.

    개발 경험이 많지 않다면 "환경변수"를 프로그램 밖에서 넣어주는 설정값이라고
    이해하면 됩니다. 비밀번호나 API key처럼 코드에 직접 쓰면 위험한 값은
    보통 환경변수로 관리합니다.
    """

    confluence_url: str | None = None
    confluence_id: str | None = None
    confluence_password: str | None = None

    openai_api_key: str | None = None
    llm_evaluation_models: str = "gpt-4.1,gpt-4.1-mini,o4-mini"
    llm_aggregator_model: str = "gpt-4.1"
    llm_timeout_seconds: int = 120
    llm_max_retries: int = 2
    llm_temperature: float = 0

    app_database_path: str = "./data/app.db"
    allow_demo_fallback: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_path(self) -> Path:
        """문자열로 받은 DB 경로를 Path 객체로 바꿔 줍니다."""

        return Path(self.app_database_path)

    @property
    def evaluation_model_names(self) -> list[str]:
        """쉼표로 구분된 모델명을 Python list로 변환합니다."""

        return [
            model_name.strip()
            for model_name in self.llm_evaluation_models.split(",")
            if model_name.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    """설정 객체를 한 번만 만들고 재사용합니다.

    `lru_cache` 덕분에 매 요청마다 .env 파일을 다시 읽지 않아도 됩니다.
    """

    return Settings()
