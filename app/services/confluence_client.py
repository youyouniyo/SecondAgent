import re
from dataclasses import dataclass

from app.config import get_settings


@dataclass
class ConfluencePage:
    """Confluence에서 읽어온 페이지 정보를 담는 작은 데이터 상자입니다."""

    page_id: str
    title: str
    html: str


class ConfluencePageReader:
    """Confluence page URL을 받아 실제 문서 본문을 읽어오는 클래스입니다."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def fetch_page(self, page_url: str) -> ConfluencePage:
        """URL에서 page id를 찾고 Confluence API로 본문을 가져옵니다.

        로컬 개발 중에는 Confluence 계정이나 API Token이 아직 없을 수 있습니다.
        그래서 `ALLOW_DEMO_FALLBACK=true`일 때는 실제 호출 대신 샘플 문서를 반환합니다.
        이 fallback은 개발자가 화면과 DB 흐름을 먼저 확인할 수 있게 해주는 장치입니다.
        """

        if self._should_use_demo_page(page_url):
            return self._demo_page(page_url)

        page_id = self._extract_page_id(page_url)
        if not page_id:
            raise ValueError("Confluence URL에서 page ID를 찾지 못했습니다.")

        if not (
            self.settings.confluence_url
            and self.settings.confluence_id
            and self.settings.confluence_password
        ):
            raise RuntimeError("CONFLUENCE_URL, CONFLUENCE_ID, CONFLUENCE_PASSWORD 환경변수가 필요합니다.")

        # 외부 패키지는 실제 호출이 필요할 때만 import합니다.
        # 이렇게 하면 패키지를 설치하기 전에도 나머지 코드 구조를 읽고 테스트하기 쉽습니다.
        from atlassian import Confluence

        confluence = Confluence(
            url=self.settings.confluence_url,
            username=self.settings.confluence_id,
            password=self.settings.confluence_password,
        )
        page = confluence.get_page_by_id(page_id, expand="body.storage")
        html = page["body"]["storage"]["value"]
        title = page.get("title") or "제목 없는 Confluence 문서"
        return ConfluencePage(page_id=page_id, title=title, html=html)

    def _extract_page_id(self, page_url: str) -> str | None:
        """여러 Confluence URL 형식에서 page id를 최대한 찾아냅니다."""

        patterns = [
            r"/pages/(\d+)",
            r"[?&]pageId=(\d+)",
            r"/spaces/[^/]+/pages/(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, page_url)
            if match:
                return match.group(1)
        return None

    def _should_use_demo_page(self, page_url: str) -> bool:
        """demo URL이거나 환경변수가 부족하면 샘플 문서를 사용할지 판단합니다."""

        has_confluence_env = bool(
            self.settings.confluence_url
            and self.settings.confluence_id
            and self.settings.confluence_password
        )
        return self.settings.allow_demo_fallback and (
            "demo" in page_url.lower() or not has_confluence_env
        )

    def _demo_page(self, page_url: str) -> ConfluencePage:
        """실제 Confluence 없이도 동작 확인이 가능한 샘플 문서입니다."""

        return ConfluencePage(
            page_id="demo",
            title="API 장애 대응 절차",
            html=f"""
            <h1>API 장애 대응 절차</h1>
            <p>이 문서는 샘플 URL({page_url})로 생성된 데모 문서입니다.</p>
            <h2>1. 장애 확인</h2>
            <p>적절히 확인하고 조치한다.</p>
            <h2>2. 영향도 판단</h2>
            <p>문제가 크면 담당자에게 공유한다.</p>
            <h2>3. 후속 처리</h2>
            <p>필요한 경우 개선한다.</p>
            """,
        )
