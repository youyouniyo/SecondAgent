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

const criteriaManageState = {
  versions: [],
  currentVersion: null,
  selectedItemId: null,
  editingItemId: null,
  editingDetailId: null,
};

async function readError(response) {
  const text = await response.text();
  try {
    const data = JSON.parse(text);
    return data.detail || text;
  } catch {
    return text || "요청 처리 중 오류가 발생했습니다.";
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  if (response.status === 204) return null;
  return response.json();
}

async function putJson(url, body = {}) {
  return requestJson(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function deleteJson(url) {
  return requestJson(url, { method: "DELETE" });
}

async function setupAdminCriteriaManagePage() {
  const versionSelect = document.getElementById("versionSelect");
  if (!versionSelect) return;
  await loadCriteriaVersions();
}

async function loadCriteriaVersions(selectedVersionId = null) {
  const versions = await requestJson("/api/admin/criteria/versions");
  criteriaManageState.versions = versions;
  renderVersionSelect(selectedVersionId);
  renderVersionsTable();

  const versionId = selectedVersionId || versions[0]?.id;
  if (versionId) {
    document.getElementById("versionSelect").value = String(versionId);
    await loadVersionDetail(versionId);
  }
}

function renderVersionSelect(selectedVersionId) {
  const select = document.getElementById("versionSelect");
  select.innerHTML = `<option value="">버전을 선택하세요...</option>`;
  criteriaManageState.versions.forEach((version) => {
    const option = document.createElement("option");
    option.value = version.id;
    option.textContent = `${version.version_name} (${statusLabel(version.status)})`;
    if (selectedVersionId && Number(selectedVersionId) === version.id) {
      option.selected = true;
    }
    select.appendChild(option);
  });
}

function statusLabel(status) {
  const labels = { draft: "작성 중", active: "활성", archived: "보관", locked: "잠김" };
  return labels[status] || status;
}

function renderVersionsTable() {
  const tbody = document.getElementById("versionsTableBody");
  if (!criteriaManageState.versions.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">등록된 기준 버전이 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = criteriaManageState.versions.map((version) => {
    const isDraft = version.status === "draft";
    const isActive = version.status === "active";
    const canDelete = version.status === "draft" || version.status === "archived";
    return `
      <tr>
        <td>${escapeHtml(version.version_name)}</td>
        <td><span class="status-badge status-${escapeHtml(version.status)}">${statusLabel(version.status)}</span></td>
        <td>${version.item_count}</td>
        <td>${new Date(version.created_at).toLocaleString()}</td>
        <td>
          <div class="button-group">
            <button class="btn-small" onclick="selectVersion(${version.id})">보기</button>
            <button class="btn-small" onclick="duplicateVersion(${version.id})">복제</button>
            ${isDraft ? `<button class="btn-small" onclick="activateVersion(${version.id})">활성화</button>` : ""}
            ${!isActive ? `<button class="btn-small" onclick="archiveVersion(${version.id})">보관</button>` : ""}
            ${canDelete ? `<button class="btn-small btn-danger" onclick="deleteVersion(${version.id})">삭제</button>` : ""}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

async function selectVersion(versionId) {
  document.getElementById("versionSelect").value = String(versionId);
  await loadVersionDetail(versionId);
}

async function loadVersionDetail(versionId) {
  if (!versionId) return;
  const version = await requestJson(`/api/admin/criteria/versions/${versionId}`);
  criteriaManageState.currentVersion = version;
  criteriaManageState.selectedItemId = version.items[0]?.id || null;
  renderItemsTable();
  renderDetailsTable();
}

function renderItemsTable() {
  const version = criteriaManageState.currentVersion;
  const tbody = document.getElementById("itemsTableBody");
  const isDraft = version?.status === "draft";
  document.getElementById("addItemBtn").style.display = isDraft ? "inline-flex" : "none";

  if (!version) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">버전을 선택하세요.</td></tr>`;
    return;
  }
  if (!version.items.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">평가항목이 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = version.items.map((item) => `
    <tr>
      <td>${escapeHtml(item.name)}</td>
      <td>${escapeHtml(item.description)}</td>
      <td>${item.display_order}</td>
      <td>${item.details.length}</td>
      <td>
        <div class="button-group">
          <button class="btn-small" onclick="selectItem(${item.id})">내용 관리</button>
          ${isDraft ? `<button class="btn-small" onclick="showEditItemModal(${item.id})">수정</button>` : ""}
          ${isDraft ? `<button class="btn-small btn-danger" onclick="deleteItem(${item.id})">삭제</button>` : ""}
        </div>
      </td>
    </tr>
  `).join("");
}

function renderDetailsTable() {
  const version = criteriaManageState.currentVersion;
  const item = findSelectedItem();
  const tbody = document.getElementById("detailsTableBody");
  const isDraft = version?.status === "draft";

  document.getElementById("addDetailBtn").style.display = item && isDraft ? "inline-flex" : "none";
  document.getElementById("detailsInfo").style.display = item ? "block" : "none";
  document.getElementById("selectedItemName").textContent = item?.name || "";

  if (!item) {
    tbody.innerHTML = `<tr><td colspan="3" class="empty-state">항목을 선택하세요.</td></tr>`;
    document.getElementById("weightValidation").style.display = "none";
    return;
  }
  if (!item.details.length) {
    tbody.innerHTML = `<tr><td colspan="3" class="empty-state">평가내용이 없습니다.</td></tr>`;
  } else {
    tbody.innerHTML = item.details.map((detail) => `
      <tr>
        <td>${escapeHtml(detail.evaluation_content)}</td>
        <td>${detail.weight}%</td>
        <td>
          <div class="button-group">
            ${isDraft ? `<button class="btn-small" onclick="showEditDetailModal(${detail.id})">수정</button>` : ""}
            ${isDraft ? `<button class="btn-small btn-danger" onclick="deleteDetail(${detail.id})">삭제</button>` : ""}
          </div>
        </td>
      </tr>
    `).join("");
  }
  validateSelectedItemWeights();
}

function findSelectedItem() {
  const version = criteriaManageState.currentVersion;
  if (!version || !criteriaManageState.selectedItemId) return null;
  return version.items.find((item) => item.id === criteriaManageState.selectedItemId) || null;
}

function selectItem(itemId) {
  criteriaManageState.selectedItemId = itemId;
  switchTab("details-tab");
  renderDetailsTable();
}

function switchTab(tabId) {
  document.querySelectorAll(".tab-button").forEach((button) => button.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach((content) => content.classList.remove("active"));
  document.querySelector(`[onclick="switchTab('${tabId}')"]`)?.classList.add("active");
  document.getElementById(tabId)?.classList.add("active");
}

function showModal(id) {
  document.getElementById(id).classList.add("active");
}

function closeModal(id) {
  document.getElementById(id).classList.remove("active");
}

function showCreateVersionModal() {
  document.getElementById("newVersionName").value = "";
  showModal("createVersionModal");
}

async function createVersion() {
  const versionName = document.getElementById("newVersionName").value.trim();
  if (!versionName) return alert("버전명을 입력하세요.");
  try {
    const version = await postJson("/api/admin/criteria/versions", { version_name: versionName });
    closeModal("createVersionModal");
    await loadCriteriaVersions(version.id);
  } catch (error) {
    alert(error.message);
  }
}

async function duplicateVersion(versionId) {
  const source = criteriaManageState.versions.find((version) => version.id === versionId);
  const versionName = prompt("복제할 새 버전명을 입력하세요.", `${source?.version_name || "평가 기준"} 복사본`);
  if (!versionName) return;
  try {
    const version = await postJson(`/api/admin/criteria/versions/${versionId}/duplicate`, { version_name: versionName });
    await loadCriteriaVersions(version.id);
  } catch (error) {
    alert(error.message);
  }
}

async function activateVersion(versionId) {
  if (!confirm("가중치 검증을 통과한 경우 이 버전을 활성 기준으로 배포합니다.")) return;
  try {
    await postJson(`/api/admin/criteria/versions/${versionId}/activate`);
    await loadCriteriaVersions(versionId);
  } catch (error) {
    alert(error.message);
  }
}

async function archiveVersion(versionId) {
  if (!confirm("이 버전을 보관 처리할까요?")) return;
  try {
    await postJson(`/api/admin/criteria/versions/${versionId}/archive`);
    await loadCriteriaVersions(versionId);
  } catch (error) {
    alert(error.message);
  }
}

async function deleteVersion(versionId) {
  if (!confirm("이 기준 버전을 삭제할까요? 평가에 사용된 버전은 삭제할 수 없습니다.")) return;
  try {
    await deleteJson(`/api/admin/criteria/versions/${versionId}`);
    await loadCriteriaVersions();
  } catch (error) {
    alert(error.message);
  }
}

function showAddItemModal() {
  criteriaManageState.editingItemId = null;
  document.getElementById("itemModalTitle").textContent = "평가항목 추가";
  document.getElementById("itemName").value = "";
  document.getElementById("itemDescription").value = "";
  document.getElementById("itemOrder").value = criteriaManageState.currentVersion.items.length + 1;
  showModal("itemModal");
}

function showEditItemModal(itemId) {
  const item = criteriaManageState.currentVersion.items.find((entry) => entry.id === itemId);
  if (!item) return;
  criteriaManageState.editingItemId = itemId;
  document.getElementById("itemModalTitle").textContent = "평가항목 수정";
  document.getElementById("itemName").value = item.name;
  document.getElementById("itemDescription").value = item.description;
  document.getElementById("itemOrder").value = item.display_order;
  showModal("itemModal");
}

async function saveItem() {
  const version = criteriaManageState.currentVersion;
  if (!version) return;
  const payload = {
    name: document.getElementById("itemName").value.trim(),
    description: document.getElementById("itemDescription").value.trim(),
    display_order: Number(document.getElementById("itemOrder").value),
  };
  if (!payload.name || !payload.description || !payload.display_order) {
    return alert("항목명, 설명, 순서를 모두 입력하세요.");
  }

  try {
    if (criteriaManageState.editingItemId) {
      await putJson(`/api/admin/criteria/items/${criteriaManageState.editingItemId}`, payload);
    } else {
      await postJson(`/api/admin/criteria/versions/${version.id}/items`, payload);
    }
    closeModal("itemModal");
    await loadVersionDetail(version.id);
  } catch (error) {
    alert(error.message);
  }
}

async function deleteItem(itemId) {
  if (!confirm("이 평가항목과 하위 평가내용을 삭제할까요?")) return;
  try {
    await deleteJson(`/api/admin/criteria/items/${itemId}`);
    await loadVersionDetail(criteriaManageState.currentVersion.id);
  } catch (error) {
    alert(error.message);
  }
}

function showAddDetailModal() {
  criteriaManageState.editingDetailId = null;
  document.getElementById("detailModalTitle").textContent = "평가내용 추가";
  document.getElementById("detailContent").value = "";
  document.getElementById("detailWeight").value = "";
  showModal("detailModal");
}

function showEditDetailModal(detailId) {
  const item = findSelectedItem();
  const detail = item?.details.find((entry) => entry.id === detailId);
  if (!detail) return;
  criteriaManageState.editingDetailId = detailId;
  document.getElementById("detailModalTitle").textContent = "평가내용 수정";
  document.getElementById("detailContent").value = detail.evaluation_content;
  document.getElementById("detailWeight").value = detail.weight;
  showModal("detailModal");
}

async function saveDetail() {
  const item = findSelectedItem();
  if (!item) return alert("평가항목을 먼저 선택하세요.");
  const payload = {
    evaluation_content: document.getElementById("detailContent").value.trim(),
    weight: Number(document.getElementById("detailWeight").value),
  };
  if (!payload.evaluation_content || Number.isNaN(payload.weight) || payload.weight < 0 || payload.weight > 100) {
    return alert("평가내용과 0~100 사이의 가중치를 입력하세요.");
  }

  try {
    if (criteriaManageState.editingDetailId) {
      await putJson(`/api/admin/criteria/items/details/${criteriaManageState.editingDetailId}`, payload);
    } else {
      await postJson(`/api/admin/criteria/items/${item.id}/details`, payload);
    }
    closeModal("detailModal");
    await loadVersionDetail(criteriaManageState.currentVersion.id);
    criteriaManageState.selectedItemId = item.id;
    renderDetailsTable();
  } catch (error) {
    alert(error.message);
  }
}

async function deleteDetail(detailId) {
  if (!confirm("이 평가내용을 삭제할까요?")) return;
  const selectedItemId = criteriaManageState.selectedItemId;
  try {
    await deleteJson(`/api/admin/criteria/items/details/${detailId}`);
    await loadVersionDetail(criteriaManageState.currentVersion.id);
    criteriaManageState.selectedItemId = selectedItemId;
    renderDetailsTable();
  } catch (error) {
    alert(error.message);
  }
}

async function validateSelectedItemWeights() {
  const item = findSelectedItem();
  const box = document.getElementById("weightValidation");
  if (!item) return;
  try {
    const result = await requestJson(`/api/admin/criteria/items/${item.id}/weights-valid`);
    box.style.display = "block";
    box.className = `weight-info ${result.valid ? "weight-valid" : "weight-warning"}`;
    box.textContent = result.message;
  } catch {
    box.style.display = "none";
  }
}

setupMainPage();
setupProgressPage();
setupResultPage();
setupAdminPage();
setupCriteriaPage();
setupAdminCriteriaManagePage();
