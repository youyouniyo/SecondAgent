from bs4 import BeautifulSoup, NavigableString


def normalize_document(html: str) -> tuple[str, dict]:
    """Confluence HTML을 LLM이 읽기 쉬운 텍스트와 구조 정보로 바꿉니다.

    - preview 화면에는 HTML 구조가 필요합니다.
    - LLM 평가에는 불필요한 태그보다 텍스트와 제목 구조가 더 중요합니다.

    그래서 이 함수는 같은 문서를 두 가지 형태로 나눠 준비합니다.
    """

    soup = BeautifulSoup(html, "html.parser")
    lines: list[str] = []
    headings: list[dict] = []

    for element in soup.find_all(["h1", "h2", "h3", "p", "li"]):
        text = element.get_text(" ", strip=True)
        if not text:
            continue

        if element.name in {"h1", "h2", "h3"}:
            level = int(element.name[1])
            headings.append({"level": level, "text": text})
            lines.append(f"{'#' * level} {text}")
        else:
            lines.append(text)

    normalized_text = "\n".join(lines)
    structure = {
        "headings": headings,
        "text_length": len(normalized_text),
        "paragraph_count": len(soup.find_all("p")),
        "list_item_count": len(soup.find_all("li")),
    }
    return normalized_text, structure


def replace_first_html_text(html: str, before: str, after: str) -> str:
    """HTML 안에서 첫 번째로 발견되는 문구만 바꿉니다.

    실제 Confluence 문서는 같은 단어가 여러 번 나올 수 있습니다.
    초기 구현에서는 LLM이 제안한 순서대로 첫 번째 문구를 바꾸고,
    이후 고도화 때는 Confluence storage format의 위치 정보까지 함께 저장하면 됩니다.
    """

    soup = BeautifulSoup(html, "html.parser")
    for text_node in soup.find_all(string=True):
        if before in text_node:
            text_node.replace_with(text_node.replace(before, after, 1))
            return str(soup)
    return html


def build_highlighted_html(original_html: str, suggestions: list[dict]) -> str:
    """수정 제안 상태에 따라 preview HTML에 하이라이트를 입힙니다.

    - 아직 반영하지 않은 제안은 노란색(`ai-pending`)으로 표시합니다.
    - 반영한 제안은 추천 문구로 바꾼 뒤 파란색(`ai-applied`)으로 표시합니다.

    이 함수는 매번 원본 HTML에서 다시 preview를 만들기 때문에,
    여러 번 반영/원복해도 HTML이 꼬이는 문제를 줄일 수 있습니다.
    """

    soup = BeautifulSoup(original_html, "html.parser")
    for suggestion in suggestions:
        original_text = suggestion["original_text"]
        status = suggestion.get("status", "pending")
        visible_text = suggestion["recommended_text"] if status == "applied" else original_text
        css_class = "ai-applied" if status == "applied" else "ai-pending"
        wrap_first_text(soup, original_text, visible_text, css_class)
    return str(soup)


def wrap_first_text(soup: BeautifulSoup, target: str, replacement: str, css_class: str) -> bool:
    """HTML 문서에서 특정 문구 첫 번째 위치를 span으로 감쌉니다."""

    for text_node in soup.find_all(string=True):
        if target not in text_node:
            continue

        before, _, after = str(text_node).partition(target)
        span = soup.new_tag("span")
        span["class"] = css_class
        span.string = replacement

        new_nodes = []
        if before:
            new_nodes.append(NavigableString(before))
        new_nodes.append(span)
        if after:
            new_nodes.append(NavigableString(after))

        text_node.replace_with(*new_nodes)
        return True
    return False
