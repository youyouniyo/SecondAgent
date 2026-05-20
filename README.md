# Confluence AI Readability Agent

Confluence page URL을 입력하면 문서를 가져와 AI-readable 기준으로 평가하고, 수정 제안과 점수를 보여주는 초기 구현입니다.

## 실행 방법

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

실행 후 브라우저에서 `http://127.0.0.1:8000`으로 접속하면 됩니다.

현재 PC처럼 `python` 명령이 없고 `uv`만 설치된 환경에서는 아래 명령으로 실행할 수 있습니다.

```powershell
uv run --python 3.12 --with-requirements requirements.txt uvicorn app.main:app --reload
```

## 주요 화면

- `/`: 사용자 Main 화면
- `/progress/{job_id}`: 평가중 화면
- `/result/{result_id}`: 평가 결과 화면
- `/admin`: Admin Dashboard
- `/admin/criteria`: 평가 기준 관리 화면

## 개발 메모

- 초기 버전은 SQLite를 사용합니다.
- Admin 권한은 `users` 테이블의 `role` 값을 직접 `admin`으로 바꿔 관리합니다.
- Confluence 직접 수정은 하지 않고, 결과 화면의 본문 Copy를 통해 사용자가 직접 반영합니다.
- `OPENAI_API_KEY` 또는 Confluence 환경변수가 없으면 로컬 확인을 위해 demo fallback이 동작합니다.
