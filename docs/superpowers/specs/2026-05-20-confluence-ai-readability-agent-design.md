# Confluence AI Readability 평가 Agent 상세 설계

## 1. 개요

이 문서는 사용자가 Confluence page URL을 입력하면 해당 문서를 읽어와 AI-readable한 문서인지 평가하고, 수정이 필요한 문구와 AI추천 문구를 제안하는 Agent 서비스의 상세 설계를 정의한다.

서비스의 핵심 목표는 다음과 같다.

- Confluence 문서를 사람이 아닌 AI Agent도 안정적으로 이해할 수 있는 형태인지 평가한다.
- Admin이 평가 기준을 버전 단위로 관리할 수 있게 한다.
- 여러 LLM이 독립적으로 평가하고, 의견 차이가 큰 항목은 Aggregator(최종 재판정 LLM)가 다시 판단하게 한다.
- 결과 화면에서 원문 구조를 최대한 유지하면서 수정 필요 문구를 하이라이트한다.
- 사용자가 AI추천 문구를 preview에 반영하거나 원복할 수 있게 한다.
- 사용자의 반영/원복 상태, 평가 이력, 모델별 평가 결과, 포인트 이력을 저장한다.

초기 구현은 내부 사용을 전제로 하며, Confluence 직접 수정 기능은 포함하지 않는다.

## 2. 주요 사용자와 권한

### 일반 사용자

일반 사용자는 다음 기능을 사용할 수 있다.

- Confluence page URL 입력
- 평가 요청
- 평가중 화면 확인
- 최종결과 화면 확인
- AI추천 문구 반영/원복
- 본문 Copy
- 평가 결과 확정
- 후기 작성

일반 사용자는 과거 평가 이력 목록을 조회하지 않는다. 평가는 완료 직후 결과 화면에서만 확인한다.

### Admin

Admin은 다음 기능을 사용할 수 있다.

- Admin Dashboard 조회
- 평가 기준 관리
- 평가 이력 전체 조회
- 시스템 설정 조회

초기 버전에서는 Admin 권한 관리 화면을 제공하지 않는다. Admin 권한은 DB 테이블에 직접 입력해서 관리한다.

권한 판단은 애플리케이션에서 수행한다.

- `role = user`: Main, 평가중, 최종결과 화면 접근 가능
- `role = admin`: 일반 사용자 기능 + Admin Dashboard, 평가 기준 관리, 평가 이력, 시스템 설정 접근 가능

모든 Admin API는 `role == admin` 검증을 반드시 수행한다.

## 3. 전체 화면 흐름

서비스의 기본 사용자 흐름은 다음과 같다.

1. 사용자가 Main 화면에서 Confluence page URL을 입력한다.
2. `평가 시작` 버튼을 클릭한다.
3. 평가 Job이 생성된다.
4. 사용자는 별도 평가중 화면으로 이동한다.
5. 서버는 Confluence 페이지를 읽고, 문서 구조를 분석하고, 여러 LLM 평가를 수행한다.
6. 평가가 완료되면 최종결과 화면으로 이동한다.
7. 사용자는 수정 제안을 검토하고, AI추천 문구를 반영하거나 원복한다.
8. 사용자는 본문 Copy를 통해 수정된 preview 본문을 복사할 수 있다.
9. 사용자는 결과를 확정한다.
10. 확정 후 후기 작성이 가능하다.

Admin 흐름은 다음과 같다.

1. Admin이 Admin Dashboard에 접근한다.
2. 운영 지표, 최근 평가 이력, 운영 알림을 확인한다.
3. 평가 기준 관리, 평가 이력, 시스템 설정 화면으로 이동한다.
4. 평가 기준은 버전 단위로 관리한다.
5. 평가에 사용된 기준 버전은 수정하거나 삭제할 수 없다.
6. 변경이 필요하면 기존 버전을 복제해 새 버전을 만든다.

## 4. Main 화면 설계

Main 화면은 사용자 진입 화면이다.

### 상단 URL 입력 영역

상단에는 사용자가 Confluence page URL을 입력할 수 있는 입력칸을 둔다.

구성 요소:

- 서비스명 또는 짧은 설명
- Confluence URL 입력칸
- `평가 시작` 버튼
- 지원 URL 안내
- 예상 소요 시간 안내

예상 안내 문구:

```text
Confluence page URL을 입력하면 문서 구조와 표현을 분석합니다.
예상 소요 시간: 약 30초-2분
```

### 하단 홍보/가이드 영역

URL 입력 영역 아래에는 AI-readable 문서 작성 가이드를 넓은 카드형 영역으로 보여준다.

포함할 가이드:

- 명확한 구조
- 구체적 조건
- 일관된 용어
- 실행 가능한 절차

각 가이드 카드는 텍스트 설명과 이해를 돕는 이미지형 예시를 포함한다.

Main 화면에는 평가 결과 요약 홍보 패널을 두지 않는다.

## 5. 평가중 화면 설계

평가 시작 후 사용자는 별도 평가중 화면으로 이동한다.

### 목적

평가가 오래 걸릴 수 있으므로 사용자가 현재 진행 상황을 이해하고 기다릴 수 있게 한다.

### 화면 구성

주요 문구:

```text
평가중입니다

Confluence 문서를 읽고 AI-readable 기준으로 분석하고 있습니다.
여러 LLM이 독립적으로 평가한 뒤, 의견 차이가 큰 항목은 한 번 더 검토합니다.
```

표시 정보:

- 평가 대상 URL
- 현재 단계
- 진행률 bar
- 단계별 상태
- 예상 소요 시간
- `평가 취소` 버튼

### 평가 상태값

평가 Job 상태는 다음 값을 사용한다.

- `queued`: 평가 대기
- `fetching_confluence`: Confluence 페이지 불러오는 중
- `parsing_document`: 문서 구조 분석 중
- `evaluating_models`: 여러 LLM 독립 평가 중
- `aggregating`: 모델 간 의견 차이 확인 및 Aggregator 재판정 중
- `completed`: 평가 완료
- `failed`: 평가 실패
- `cancelled`: 평가 취소

## 6. 최종결과 화면 설계

최종결과 화면은 평가 리포트와 문서 리뷰 기능을 함께 제공한다.

### 상단 액션 영역

상단 오른쪽에는 `새 평가 시작하기` 버튼을 둔다.

동작:

- Main 화면으로 이동
- 기존 평가 결과와 반영/원복 상태는 DB에 유지
- URL 입력칸은 비워진 상태로 시작

### 상단 결과 요약 영역

상단에는 두 개의 동일한 크기 카드가 배치된다.

왼쪽 카드: `문서 전체 평가 요약`

- 문서 제목
- 평가 기준 버전
- 평가 완료 시각
- AI-readable 판정
- 3-5줄 전체 요약
- 전체 점수
- 전체 등급
- 주요 리스크

오른쪽 카드: `평가 항목별 점수표`

- 평가항목명
- 최종 점수
- 등급

모델별 점수와 Aggregator 재판정 상세는 기본 화면에 바로 노출하지 않는다. 필요 시 Admin 평가 이력 상세에서 조회한다.

### Confluence page preview 영역

왼쪽 본문 영역에는 Confluence 원문을 복사한 preview를 표시한다.

요구사항:

- Confluence 원문 구조를 최대한 유지한다.
- 제목, 폰트 크기, 표, 목록 구조를 최대한 유지한다.
- 수정이 필요한 문구는 노란색 하이라이트로 표시한다.
- AI추천 문구를 반영한 경우 파란색 하이라이트로 변경한다.
- 선택 중인 문구는 outline 등으로 강조할 수 있다.
- `본문 Copy` 버튼은 `Confluence page preview` 영역의 우측 상단에 배치한다.

`본문 Copy` 버튼 동작:

- 현재 preview에 반영된 본문 내용을 클립보드에 복사한다.
- 사용자는 복사한 내용을 Confluence에 직접 붙여넣어 반영한다.
- 이 서비스는 Confluence 원문을 직접 업데이트하지 않는다.

### 오른쪽 문구별 수정 제안 패널

오른쪽 패널에는 문서 위치 순서대로 수정 제안 카드를 표시한다.

초기 버전에서는 필터, 검색, 평가항목별 그룹핑을 제공하지 않는다.

각 카드 구성:

- 수정 대상 문구
- 평가항목
- 평가 내용
- 분석결과
- AI추천
- `반영하기` 버튼
- `원복하기` 버튼
- 저장 상태

카드 클릭 동작:

- 해당 문구가 있는 preview 위치로 자동 스크롤한다.

### 반영/원복 동작

`반영하기` 클릭 시:

- preview의 해당 문구가 AI추천 문구로 변경된다.
- 하이라이트 색상이 파란색으로 변경된다.
- 제안 상태가 `applied`로 변경된다.
- 변경 상태를 즉시 DB에 자동 저장한다.
- 저장 성공 시 상태 카운트를 갱신한다.

`원복하기` 클릭 시:

- preview의 해당 문구가 원문으로 복구된다.
- 하이라이트 색상이 노란색으로 변경된다.
- 제안 상태가 `reverted` 또는 `pending`으로 변경된다.
- 변경 상태를 즉시 DB에 자동 저장한다.

자동 저장 실패 시:

- UI 상태를 이전 상태로 되돌린다.
- 해당 카드에 오류 메시지를 표시한다.
- `다시 시도` 버튼을 제공한다.

### 확정 영역

결과 화면 하단에는 확정 전 안내 영역을 둔다.

안내 문구:

```text
수정 된 페이지는 컨플런스에 직접 반영이 불가하여 본문을 Copy하여 직접 반영이 필요 합니다.
확정 후에는 현재 반영/원복 상태가 저장되고 포인트가 적립됩니다.
```

확정 버튼:

- 하단 안내 영역 우측에 배치한다.
- 일반 버튼보다 넓게 표시한다.
- Confluence에 직접 반영하지 않는다.
- 검토 완료 상태를 저장한다.
- 확정 포인트를 지급한다.
- 후기 작성을 유도한다.

## 7. Admin Dashboard 설계

Admin Dashboard는 운영 현황을 한 화면에서 보여주고 각 관리 화면으로 이동하는 허브 역할을 한다.

### 상단 지표

상단에는 다음 운영 지표를 표시한다.

- 오늘 평가
- 일일 평가자수
- 평균 점수
- AI추천용어 적용율
- Aggregator 재판정 비율
- 활성 기준 버전

`일일 평가자수`는 오늘 평가를 수행한 고유 사용자 수이다.

`AI추천용어 적용율`은 전체 AI추천 중 사용자가 `반영하기`로 적용한 비율이다.

### 관리 진입 카드

Dashboard에는 다음 관리 진입 카드를 둔다.

- 평가 기준 관리
- 평가 이력
- 시스템 설정

### 최근 평가 이력

최근 평가 목록을 간략히 표시한다.

표시 항목:

- 문서명
- 점수
- 등급
- 상태

### 운영 알림

운영 알림에는 다음 정보를 표시한다.

- 최근 실패 평가
- 기준 버전 상태
- LLM 모델 상태
- Confluence 연결 상태

## 8. 평가 기준 관리 설계

평가 기준은 버전 단위로 관리한다.

### 기준 버전 정책

- 활성 기준 버전은 하나만 존재한다.
- 평가 실행 시 사용된 기준 버전 ID를 결과에 저장한다.
- 평가에 한 번이라도 사용된 기준 버전은 수정할 수 없다.
- 평가에 사용된 기준 버전은 삭제할 수 없다.
- 기준 변경이 필요하면 기존 버전을 복제해서 새 버전을 만든다.
- 더 이상 사용하지 않는 기준 버전은 보관 처리한다.
- 가중치 검증을 통과해야 활성 버전으로 배포할 수 있다.

### 평가 기준 구조

평가 기준은 다음 계층으로 구성된다.

- 평가 기준 버전
- 평가항목
- 평가내용
- 평가내용별 가중치

한 평가항목 안의 평가내용별 가중치 합계는 100%여야 한다.

### 다중 LLM 평가 설정

Admin은 다중 LLM 평가 설정을 관리할 수 있다.

설정 항목:

- 기본 불일치 threshold
- 평가항목별 개별 threshold
- 최종 점수 기본값: 평균 또는 중앙값
- 재판정 방식: 불일치 항목만 Aggregator 재판정 또는 전체 항목 Aggregator 검토

초기 정책:

- 기본 최종 점수는 평균/중앙값 기반으로 계산한다.
- 모델 간 점수 차이가 Admin threshold 이상이면 Aggregator가 해당 항목을 재판정한다.

## 9. 평가 이력 관리

일반 사용자는 평가 이력 목록을 조회하지 않는다.

Admin은 전체 평가 이력을 조회할 수 있다.

평가 이력에서 조회할 수 있는 정보:

- 평가 요청 일시
- 요청 사용자
- Confluence URL
- 문서 제목
- 평가 기준 버전
- 전체 점수
- 전체 등급
- 평가 상태
- 사용된 LLM 모델 목록
- Aggregator 재판정 여부
- 실패 사유
- 모델별 raw response
- 모델별 parsed response
- 최종 결과
- 제안 반영/원복 상태

## 10. 포인트와 후기 정책

평가를 독려하기 위해 포인트를 지급한다.

### 포인트 지급 기준

- 문서 평가 요청: 1점
- 평가 결과 확정: 2점
- 후기 작성: 5점
- 유효 후기 보너스: 5점

### 중복 지급 제한

문서 평가 요청 포인트:

- 같은 사용자 + 같은 Confluence URL + 같은 날짜 기준 1회만 지급한다.

평가 결과 확정 포인트:

- `evaluation_result_id` 기준 1회만 지급한다.

후기 작성 포인트:

- `evaluation_result_id` 기준 1회만 지급한다.

유효 후기 보너스:

- Admin이 후기를 유효하다고 표시한 경우 1회만 추가 지급한다.

### 후기

후기는 확정 후 작성할 수 있다.

후기 데이터:

- 만족도
- 코멘트
- 작성자
- 작성 시각
- 포인트 지급 여부
- 유효 후기 여부

## 11. Confluence 연동

Confluence 문서 수집은 Python 패키지 `atlassian-python-api`를 사용한다.

환경변수:

- `CONFLUENCE_URL`
- `CONFLUENCE_ID`
- `CONFLUENCE_PASSWORD`

인증 예시:

```python
from atlassian import Confluence
import os

confluence = Confluence(
    url=os.environ["CONFLUENCE_URL"],
    username=os.environ["CONFLUENCE_ID"],
    password=os.environ["CONFLUENCE_PASSWORD"],
)
```

Confluence Cloud 환경에서는 `CONFLUENCE_PASSWORD`에 실제 비밀번호 대신 Atlassian API Token을 넣을 수 있다. 단, 변수명은 `CONFLUENCE_PASSWORD`를 유지한다.

문서 수집 흐름:

1. 사용자가 Confluence page URL을 입력한다.
2. 서버가 URL에서 page ID 또는 page 식별 정보를 추출한다.
3. Confluence API로 페이지 본문을 조회한다.
4. 원문 HTML 또는 storage format은 preview 보존용으로 저장한다.
5. LLM 평가용으로는 HTML에서 텍스트, 제목 구조, 표, 목록, 링크 정보를 추출한다.

## 12. LangGraph 평가 파이프라인

평가 파이프라인은 LangGraph로 구현한다.

LLM 호출은 LangChain을 사용한다.

LLM 응답 검증은 Pydantic structured output을 사용한다.

### 그래프 흐름

```text
START
→ create_job
→ fetch_confluence_page
→ parse_document
→ load_active_criteria
→ run_parallel_llm_evaluations
→ compare_model_scores
→ needs_aggregation?
  → yes: run_aggregator
  → no: calculate_final_scores
→ generate_final_suggestions
→ save_evaluation_result
→ END
```

### Node 역할

`create_job`

- `evaluation_jobs` 생성
- 상태를 `queued`로 저장

`fetch_confluence_page`

- 환경변수 기반 계정으로 Confluence 인증
- 사용자가 입력한 page URL에서 문서 조회
- 상태를 `fetching_confluence`로 저장

`parse_document`

- preview용 원문 HTML 저장
- LLM 입력용 정규화 텍스트와 문서 구조 추출
- 상태를 `parsing_document`로 저장

`load_active_criteria`

- 활성 기준 버전 조회
- 평가항목, 평가내용, 가중치, threshold 로드

`run_parallel_llm_evaluations`

- 여러 LLM이 같은 문서와 같은 기준으로 독립 평가
- 모델별 raw response와 parsed response 저장
- 상태를 `evaluating_models`로 저장

`compare_model_scores`

- 평가항목별 평균, 중앙값, 편차 계산
- Admin threshold 초과 항목 식별

`run_aggregator`

- 편차가 큰 항목만 Aggregator가 재판정
- 재판정 이유 저장
- 상태를 `aggregating`으로 저장

`calculate_final_scores`

- 편차가 작으면 평균/중앙값 기반으로 최종 점수 산출

`generate_final_suggestions`

- 모델별 제안 병합
- 같은 원문 문구에 대한 중복 제안 병합
- 문서 위치 순서대로 정렬

`save_evaluation_result`

- 평가 결과, 항목별 점수, 최종 제안 저장
- 상태를 `completed`로 저장

### LangGraph State

```python
class EvaluationState(TypedDict):
    job_id: int
    user_id: int
    confluence_url: str
    page_id: str | None
    document_title: str | None
    original_html: str | None
    normalized_text: str | None
    document_structure: dict | None
    criteria_version_id: int | None
    criteria: dict | None
    model_results: list[dict]
    score_comparison: dict | None
    aggregation_required: bool
    aggregator_result: dict | None
    final_result: dict | None
    error: str | None
```

## 13. LLM API 호출 설정

LLM API 호출은 LangChain을 통해 수행한다.

평가 파이프라인은 LangGraph가 제어하고, 각 LLM 호출 Node는 LangChain chain으로 구성한다. LLM 응답은 Pydantic structured output으로 검증한다.

### 환경변수

초기 버전에서는 OpenAI 호환 API 사용을 기본으로 한다.

필수 환경변수:

```env
OPENAI_API_KEY=...
LLM_EVALUATION_MODELS=gpt-4.1,gpt-4.1-mini,o4-mini
LLM_AGGREGATOR_MODEL=gpt-4.1
LLM_TIMEOUT_SECONDS=120
LLM_MAX_RETRIES=2
LLM_TEMPERATURE=0
```

환경변수 설명:

- `OPENAI_API_KEY`: LLM API 호출용 key
- `LLM_EVALUATION_MODELS`: 독립 평가에 사용할 모델 목록
- `LLM_AGGREGATOR_MODEL`: Aggregator(최종 재판정 LLM)에 사용할 모델
- `LLM_TIMEOUT_SECONDS`: LLM 호출 timeout
- `LLM_MAX_RETRIES`: LLM 호출 실패 시 재시도 횟수
- `LLM_TEMPERATURE`: 평가 일관성을 위한 temperature 값

초기 기본값:

- 평가 모델 수: 3개
- Aggregator 모델 수: 1개
- temperature: `0`
- timeout: `120초`
- max retries: `2회`

### 모델 역할

LLM 모델은 다음 역할로 나뉜다.

- `evaluator`: 문서와 평가 기준을 독립적으로 평가하는 모델
- `aggregator`: 모델 간 점수 차이가 큰 항목을 최종 재판정하는 모델

각 evaluator는 같은 문서와 같은 평가 기준을 입력받지만, 서로의 결과는 보지 않는다.

Aggregator는 다음 정보를 입력받는다.

- 원문 문서 구조
- 평가 기준
- 모델별 평가 결과
- 평균 점수
- 중앙값
- 점수 편차
- Admin threshold
- 모델별 평가 근거

### LangChain 호출 예시

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model=model_name,
    temperature=0,
    timeout=120,
    max_retries=2,
)

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an AI-readable document evaluator."),
    ("user", "Document:\n{document}\n\nCriteria:\n{criteria}")
])

chain = prompt | llm.with_structured_output(EvaluationResult)

result = chain.invoke({
    "document": normalized_document,
    "criteria": criteria_json,
})
```

Aggregator 호출 예시:

```python
aggregator_llm = ChatOpenAI(
    model=aggregator_model_name,
    temperature=0,
    timeout=120,
    max_retries=2,
)

aggregator_chain = aggregator_prompt | aggregator_llm.with_structured_output(AggregatedResult)

aggregator_result = aggregator_chain.invoke({
    "document": normalized_document,
    "criteria": criteria_json,
    "model_results": model_results,
    "score_comparison": score_comparison,
})
```

### Structured output 검증

LLM 응답은 반드시 Pydantic 모델로 검증한다.

검증 실패 시 처리:

1. 같은 모델로 1회 재시도한다.
2. 재시도 실패 시 해당 모델 결과를 `failed`로 저장한다.
3. 성공한 evaluator 수가 최소 기준 이상이면 평가를 계속한다.
4. 성공한 evaluator 수가 최소 기준 미만이면 평가 Job을 실패 처리한다.

초기 최소 기준:

- 평가 모델 3개 중 2개 이상 성공하면 평가 계속
- 1개 이하만 성공하면 평가 실패

### 호출 결과 저장

각 LLM 호출 결과는 `llm_model_results`에 저장한다.

저장 항목:

- 모델명
- 모델 역할
- raw response
- parsed response
- 호출 성공/실패 여부
- 실패 사유
- 호출 시작 시각
- 호출 종료 시각

raw response는 디버깅과 품질 점검을 위해 저장하지만, 민감정보가 포함되지 않도록 prompt 구성 단계에서 Confluence 인증 정보나 환경변수 값은 절대 포함하지 않는다.

### 실패와 재시도 정책

LLM API 호출 실패 유형:

- timeout
- rate limit
- API key 오류
- 모델 응답 형식 오류
- structured output 검증 실패

처리 정책:

- timeout 또는 일시적 오류는 `LLM_MAX_RETRIES`만큼 재시도한다.
- rate limit은 짧은 backoff 후 재시도한다.
- API key 오류는 재시도하지 않고 즉시 실패 처리한다.
- structured output 검증 실패는 같은 모델로 1회 재시도한다.
- Aggregator 실패 시 평균/중앙값 기반 결과를 fallback으로 사용하고, Admin 평가 이력에 Aggregator 실패를 기록한다.

### 비용과 호출량 관리

평가 1회당 기본 LLM 호출 수:

- evaluator 모델 3회
- Aggregator 0-1회

Aggregator는 모든 평가에서 호출하지 않는다. Admin threshold 이상으로 모델 간 점수 차이가 발생한 항목이 있을 때만 호출한다.

추후 비용이 증가하면 다음 최적화를 고려한다.

- 평가 모델 수 축소
- 문서 길이에 따른 모델 선택
- 긴 문서 chunk 평가
- 동일 문서 재평가 cache
- Aggregator 호출 조건 강화

## 14. 다중 LLM 평가 전략

평가 품질을 높이기 위해 여러 LLM이 독립적으로 평가한다.

### 평가 방식

초기 방식은 Panel Review 방식으로 한다.

1. 여러 LLM이 서로의 결과를 보지 않고 독립 평가한다.
2. 시스템이 모델별 점수 차이와 제안을 비교한다.
3. 점수 차이가 threshold 이상인 항목은 Aggregator가 재판정한다.
4. 최종 결과에는 평균, 중앙값, 편차, Aggregator 재판정 여부를 저장한다.

### 점수 산출

- 각 모델은 평가항목별 0-100점 점수를 반환한다.
- 시스템은 평가항목별 평균과 중앙값을 계산한다.
- 기본 최종 점수는 중앙값을 우선 사용한다.
- 단, Admin 설정에 따라 평균을 기본값으로 사용할 수 있다.
- 점수 편차가 threshold 이상이면 Aggregator가 최종 점수를 재산정한다.

### LLM 평가 응답 JSON

```json
{
  "model_name": "model_name",
  "evaluation_summary": "문서 전체 평가 요약",
  "overall_score": 72,
  "overall_grade": "B",
  "ai_readable_status": "needs_improvement",
  "criteria_results": [
    {
      "criteria_item_id": 1,
      "criteria_name": "구조 명확성",
      "score": 84,
      "grade": "A",
      "comment": "제목과 목록 구조는 비교적 명확합니다.",
      "details": [
        {
          "criteria_detail_id": 11,
          "score": 90,
          "weight": 40,
          "comment": "제목 계층이 논리적으로 구성되어 있습니다."
        }
      ]
    }
  ],
  "suggestions": [
    {
      "criteria_item_id": 2,
      "criteria_name": "맥락 충분성",
      "original_text": "적절히 확인하고 조치한다",
      "evaluation_content": "확인 대상과 조치 기준이 모호합니다.",
      "analysis_result": "AI가 입력값과 완료 조건을 구분하기 어렵습니다.",
      "recommended_text": "알림 ID, 오류율, 영향 API를 확인한 뒤 심각도 기준에 따라 조치한다.",
      "severity": "medium",
      "document_position_hint": {
        "heading": "API 장애 대응 절차",
        "section": "1. 장애 확인",
        "order": 1
      }
    }
  ]
}
```

### Aggregator 응답 JSON

```json
{
  "final_summary": "최종 평가 요약",
  "overall_score": 72,
  "overall_grade": "B",
  "ai_readable_status": "needs_improvement",
  "criteria_scores": [
    {
      "criteria_item_id": 2,
      "criteria_name": "맥락 충분성",
      "model_scores": [
        { "model_name": "model_a", "score": 68 },
        { "model_name": "model_b", "score": 82 },
        { "model_name": "model_c", "score": 60 }
      ],
      "average_score": 70,
      "median_score": 68,
      "score_spread": 22,
      "threshold": 15,
      "aggregator_used": true,
      "final_score": 66,
      "final_grade": "C",
      "aggregator_reason": "모델 간 편차가 threshold를 초과했고, 원문에서 전제 조건 누락이 명확하므로 낮은 점수에 가깝게 조정했습니다."
    }
  ],
  "final_suggestions": [
    {
      "source_model_names": ["model_a", "model_c"],
      "criteria_item_id": 2,
      "original_text": "적절히 확인하고 조치한다",
      "evaluation_content": "확인 대상과 조치 기준이 모호합니다.",
      "analysis_result": "절차 실행에 필요한 입력값과 완료 조건이 생략되어 있습니다.",
      "recommended_text": "알림 ID, 오류율, 영향 API를 확인한 뒤 심각도 기준에 따라 조치한다.",
      "severity": "medium",
      "document_position_hint": {
        "heading": "API 장애 대응 절차",
        "section": "1. 장애 확인",
        "order": 1
      }
    }
  ]
}
```

## 15. 데이터 모델

초기 버전은 SQLite를 사용한다.

단일 서버와 소규모 내부 사용을 전제로 빠르게 개발한다. 추후 사용량이 늘면 PostgreSQL로 이전할 수 있도록 RDB 호환적인 스키마를 유지한다.

### users

- `id`
- `email`
- `name`
- `role`: `user`, `admin`
- `status`: `active`, `inactive`
- `created_at`
- `updated_at`

### criteria_versions

- `id`
- `version_name`
- `status`: `draft`, `active`, `archived`, `locked`
- `is_active`
- `locked_at`
- `published_at`
- `created_by`
- `created_at`
- `updated_at`

### criteria_items

- `id`
- `criteria_version_id`
- `name`
- `description`
- `display_order`
- `is_active`

### criteria_item_details

- `id`
- `criteria_item_id`
- `content`
- `weight`
- `display_order`
- `is_active`

### evaluation_jobs

- `id`
- `requested_by`
- `confluence_url`
- `confluence_page_id`
- `status`
- `criteria_version_id`
- `started_at`
- `completed_at`
- `failed_reason`

### evaluation_results

- `id`
- `evaluation_job_id`
- `document_title`
- `original_html`
- `normalized_text`
- `overall_score`
- `overall_grade`
- `summary`
- `ai_readable_status`
- `confirmed_at`
- `confirmed_by`
- `created_at`

### llm_model_results

- `id`
- `evaluation_result_id`
- `model_name`
- `model_role`
- `raw_response`
- `parsed_response`
- `created_at`

### criteria_scores

- `id`
- `evaluation_result_id`
- `criteria_item_id`
- `final_score`
- `final_grade`
- `average_score`
- `median_score`
- `score_spread`
- `threshold`
- `aggregator_used`
- `aggregator_reason`

### suggestions

- `id`
- `evaluation_result_id`
- `criteria_item_id`
- `original_text`
- `recommended_text`
- `current_text`
- `evaluation_content`
- `analysis_result`
- `document_position`
- `status`: `pending`, `applied`, `reverted`
- `created_at`
- `updated_at`

### suggestion_actions

- `id`
- `suggestion_id`
- `action`: `apply`, `revert`
- `before_text`
- `after_text`
- `acted_by`
- `acted_at`

### points

- `id`
- `user_id`
- `evaluation_result_id`
- `point_type`: `evaluation_request`, `result_confirm`, `review_write`, `review_bonus`
- `points`
- `reason`
- `created_at`

### reviews

- `id`
- `evaluation_result_id`
- `user_id`
- `rating`
- `comment`
- `points_awarded`
- `is_valid`
- `validated_by`
- `validated_at`
- `created_at`

## 16. 보안과 운영 정책

### Confluence 계정 정보

Confluence 계정 정보는 환경변수로 관리한다.

- `CONFLUENCE_URL`
- `CONFLUENCE_ID`
- `CONFLUENCE_PASSWORD`

비밀번호 또는 token은 로그에 출력하지 않는다.

### Admin 권한

초기 버전에서는 DB 직접 입력으로 Admin 권한을 관리한다.

사용자/권한 관리 화면은 이번 범위에서 제외한다.

### 평가 결과 접근

- 일반 사용자는 평가 직후 본인의 결과 화면만 확인한다.
- Admin은 전체 평가 이력을 조회할 수 있다.

### Confluence 직접 업데이트

초기 버전에서는 Confluence 페이지 직접 업데이트를 지원하지 않는다.

사용자는 `본문 Copy`로 수정된 preview 본문을 복사한 뒤 Confluence에 직접 반영해야 한다.

## 17. 에러 처리

### URL 형식 오류

- Main 화면에서 URL 형식을 검증한다.
- 잘못된 URL이면 평가 Job을 생성하지 않는다.

### Confluence 인증 실패

- 평가중 화면에서 실패 상태로 전환한다.
- 메시지: `Confluence 인증에 실패했습니다. 관리자에게 문의해주세요.`

### 페이지 접근 권한 없음

- 메시지: `해당 Confluence 페이지를 읽을 권한이 없습니다.`

### 페이지 없음

- 메시지: `입력한 URL에 해당하는 Confluence 페이지를 찾을 수 없습니다.`

### LLM 평가 실패

- 일부 모델만 실패한 경우, 성공한 모델 수가 최소 기준 이상이면 평가를 계속한다.
- 최소 기준 미만이면 평가 실패로 처리한다.

### Aggregator 실패

- Aggregator 실패 시 기본 평균/중앙값 기반 결과를 사용한다.
- Admin 이력에는 Aggregator 실패 로그를 남긴다.

### 자동 저장 실패

- 반영/원복 자동 저장 실패 시 UI를 이전 상태로 되돌린다.
- 제안 카드에 오류 메시지와 `다시 시도` 버튼을 표시한다.

## 18. 추후 확장

추후 확장 후보:

- Confluence 직접 업데이트
- 사용자별 평가 이력 화면
- Admin 사용자/권한 관리 화면
- PostgreSQL 이전
- 평가 기준 import/export
- Specialist Agent 구조
- 문서 유형별 평가 기준 분리
- Slack 또는 Teams 알림
- 평가 결과 PDF/HTML 내보내기
