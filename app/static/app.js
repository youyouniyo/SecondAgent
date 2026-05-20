// 이 파일은 화면에서 버튼을 눌렀을 때 서버 API를 호출하는 역할을 합니다.
// 백엔드는 Python/FastAPI가 담당하고, 이 파일은 브라우저 안에서 실행됩니다.

function getPathId(indexFromEnd = 0) {
  // URL이 /result/3 형태일 때 마지막 숫자 3을 꺼내기 위한 helper입니다.
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[parts.length - 1 - indexFromEnd];
}

async function postJson(url, body = {}) {
  // fetch를 매번 길게 쓰지 않도록 POST 요청 공통 코드를 함수로 묶었습니다.
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function setupMainPage() {
  const form = document.getElementById("evaluation-form");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const confluenceUrl = document.getElementById("confluence-url").value;
    const data = await postJson("/api/evaluations", { confluence_url: confluenceUrl });
    window.location.href = data.progress_url;
  });
}

function setupProgressPage() {
  const bar = document.getElementById("progress-bar");
  if (!bar) return;

  const jobId = getPathId();
  const steps = [
    ["fetching_confluence", "Confluence 페이지 불러오기"],
    ["parsing_document", "문서 구조 분석"],
    ["evaluating_models", "평가 기준 적용 및 여러 LLM 독립 평가"],
    ["aggregating", "모델 간 의견 차이 확인"],
    ["completed", "최종 결과 정리"],
  ];
  const timer = setInterval(async () => {
    const response = await fetch(`/api/evaluations/${jobId}`);
    const job = await response.json();

    bar.style.width = `${job.progress}%`;
    document.getElementById("progress-step").textContent = `현재 단계: ${job.current_step}`;
    document.getElementById("progress-meta").textContent = `${job.progress}%`;
    document.getElementById("progress-url").textContent = job.confluence_url;
    document.getElementById("step-list").innerHTML = steps.map(([status, label], index) => {
      const isDone = job.progress >= [15, 30, 65, 85, 100][index] || job.status === "completed";
      const isActive = job.status === status;
      const className = isDone && !isActive ? "step done" : isActive ? "step active" : "step";
      const number = isDone && !isActive ? "✓" : String(index + 1);
      const suffix = isDone && !isActive ? " 완료" : isActive ? " 중" : " 대기";
      return `<div class="${className}"><span class="step-number">${number}</span><span>${label}${suffix}</span></div>`;
    }).join("");

    if (job.status === "completed") {
      clearInterval(timer);
      window.location.href = `/result/${job.result_id}`;
    }
    if (job.status === "failed") {
      clearInterval(timer);
      document.getElementById("progress-step").textContent = job.error_message || "평가 실패";
    }
  }, 1200);
}

function escapeHtml(text) {
  // 사용자가 입력하거나 LLM이 반환한 문자열을 HTML로 직접 넣을 때 안전하게 바꿉니다.
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function setupResultPage() {
  const preview = document.getElementById("preview-body");
  if (!preview) return;

  const resultId = getPathId();
  const response = await fetch(`/api/results/${resultId}`);
  const result = await response.json();

  document.getElementById("summary").textContent = result.summary;
  document.getElementById("summary-meta").textContent = `${result.document_title} · 평가 결과 ID ${result.id} · ${new Date(result.created_at).toLocaleString()}`;
  document.getElementById("score-number").textContent = result.overall_score;
  document.getElementById("grade-letter").textContent = result.overall_grade;
  document.getElementById("score-note").innerHTML = `수정 제안 ${result.suggestions.length}개<br>주요 리스크: 모호한 동사, 생략된 조건, 복구 기준 부재`;
  preview.innerHTML = result.current_html;

  const scoreTable = document.getElementById("score-table");
  scoreTable.innerHTML = result.criteria_scores
    .map((score) => `<tr><td>${escapeHtml(score.criteria_name)}</td><td>${score.final_score}</td><td>${score.grade}</td></tr>`)
    .join("");

  const suggestions = document.getElementById("suggestions");
  document.getElementById("suggestion-count").textContent = `${result.suggestions.length}개`;
  suggestions.innerHTML = result.suggestions.map(renderSuggestion).join("");

  suggestions.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    const card = event.target.closest(".suggestion");
    if (card && !button) {
      const text = card.dataset.currentText;
      scrollPreviewToText(text);
      return;
    }
    if (!button) return;
    const suggestionId = button.dataset.suggestionId;
    const action = button.dataset.action;
    const data = await postJson(`/api/suggestions/${suggestionId}/${action}`);
    preview.innerHTML = data.current_html;
    window.location.reload();
  });

  document.getElementById("copy-body").addEventListener("click", async () => {
    await navigator.clipboard.writeText(preview.innerText);
    alert("본문을 복사했습니다.");
  });

  document.getElementById("confirm-result").addEventListener("click", async () => {
    const data = await postJson(`/api/results/${resultId}/confirm`);
    alert(data.message);
  });
}

function renderSuggestion(suggestion) {
  const actionLabel = suggestion.status === "applied" ? "원복하기" : "반영하기";
  const action = suggestion.status === "applied" ? "revert" : "apply";
  const currentText = suggestion.status === "applied" ? suggestion.recommended_text : suggestion.original_text;
  return `
    <article class="suggestion" data-current-text="${escapeHtml(currentText)}">
      <strong>${escapeHtml(suggestion.original_text)}</strong>
      <div class="suggestion-block">
        <span class="suggestion-label">평가 내용</span>
        <p class="suggestion-value">${escapeHtml(suggestion.evaluation_content)}</p>
      </div>
      <div class="suggestion-block analysis">
        <span class="suggestion-label">분석결과</span>
        <p class="suggestion-value">${escapeHtml(suggestion.analysis_result)}</p>
      </div>
      <div class="suggestion-block recommend">
        <span class="suggestion-label">AI추천</span>
        <p class="suggestion-value">${escapeHtml(suggestion.recommended_text)}</p>
      </div>
      <div class="suggestion-actions">
        <button class="button primary" data-action="${action}" data-suggestion-id="${suggestion.id}">${actionLabel}</button>
      </div>
    </article>
  `;
}

function scrollPreviewToText(text) {
  const preview = document.getElementById("preview-body");
  const walker = document.createTreeWalker(preview, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.nodeValue.includes(text)) {
      node.parentElement.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
  }
}

async function setupAdminPage() {
  const metrics = document.getElementById("admin-metrics");
  if (!metrics) return;

  const response = await fetch("/api/admin/dashboard");
  const data = await response.json();
  metrics.innerHTML = `
    <article class="metric"><div>오늘 평가</div><strong>${data.today_evaluations}</strong><span>오늘 생성된 평가</span></article>
    <article class="metric"><div>일일 평가자수</div><strong>${data.daily_evaluators}</strong><span>오늘 고유 사용자</span></article>
    <article class="metric"><div>평균 점수</div><strong>${data.average_score}</strong><span>전체 결과 기준</span></article>
    <article class="metric"><div>AI추천용어 적용율</div><strong>${data.ai_recommendation_apply_rate}%</strong><span>반영된 추천 비율</span></article>
    <article class="metric"><div>Aggregator 재판정</div><strong>${data.aggregator_reviews}</strong><span>불일치 항목 수</span></article>
    <article class="metric"><div>활성 기준 버전</div><strong>v1</strong><span>정상 배포 중</span></article>
  `;
}

async function setupCriteriaPage() {
  const list = document.getElementById("criteria-list");
  if (!list) return;

  const response = await fetch("/api/admin/criteria/active");
  const data = await response.json();
  document.getElementById("criteria-title").textContent = `${data.version_name} (${data.status})`;
  list.innerHTML = data.items
    .map((item) => `
      <article class="panel">
        <h2>${escapeHtml(item.name)}</h2>
        <p>${escapeHtml(item.description)}</p>
        <table>
          <thead><tr><th>평가 내용</th><th>가중치</th></tr></thead>
          <tbody>
            ${item.details.map((detail) => `<tr><td>${escapeHtml(detail.evaluation_content)}</td><td>${detail.weight}%</td></tr>`).join("")}
          </tbody>
        </table>
      </article>
    `)
    .join("");
}

setupMainPage();
setupProgressPage();
setupResultPage();
setupAdminPage();
setupCriteriaPage();
