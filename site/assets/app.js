const list = document.querySelector("#opportunity-list");
const keywordInput = document.querySelector("#keyword");
const ufSelect = document.querySelector("#uf");
const modalitySelect = document.querySelector("#modality");
const minValueInput = document.querySelector("#min-value");
const maxValueInput = document.querySelector("#max-value");
const situationSelect = document.querySelector("#situation");
const deadlineBeforeInput = document.querySelector("#deadline-before");
const onlyDispensaCheckbox = document.querySelector("#only-dispensa");
const onlyMeEppCheckbox = document.querySelector("#only-meepp");
let opportunities = [];
let collectionAvailable = false;
let collectionStale = false;
let currentPage = 1;
const PAGE_SIZE = 10;

const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

const normalizeText = (value) => String(value ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR");
const displayOr = (value) => value === null || value === undefined || value === "" ? "Não informado" : String(value);
const formatDate = (value) => {
  if (!value) return "Nao informado";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Nao informado" : new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo" }).format(parsed);
};
const formatCurrency = (value) => typeof value === "number" && Number.isFinite(value)
  ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(value)
  : "Nao informado";

function filteredItems() {
  const keyword = normalizeText(keywordInput.value.trim());
  const uf = ufSelect.value;
  const modality = modalitySelect ? modalitySelect.value : "";
  const minimum = minValueInput.value === "" ? null : Number(minValueInput.value);
  const maximum = maxValueInput.value === "" ? null : Number(maxValueInput.value);
  const situation = situationSelect.value;
  const deadlineBefore = deadlineBeforeInput.value;
  const onlyDispensa = onlyDispensaCheckbox ? onlyDispensaCheckbox.checked : false;
  const onlyMeEpp = onlyMeEppCheckbox ? onlyMeEppCheckbox.checked : false;

  return opportunities.filter((item) => {
    const haystack = normalizeText([item.objeto, item.orgao, item.modalidade].join(" "));
    if (keyword && !haystack.includes(keyword)) return false;
    if (uf && item.uf !== uf) return false;
    if (modality && item.modalidade !== modality) return false;
    if (onlyDispensa && !normalizeText(item.modalidade ?? "").includes("dispensa")) return false;
    if (onlyMeEpp && (typeof item.valor_estimado !== "number" || item.valor_estimado > 80000 || item.valor_estimado <= 0)) return false;
    if (minimum !== null && (typeof item.valor_estimado !== "number" || item.valor_estimado < minimum)) return false;
    if (maximum !== null && (typeof item.valor_estimado !== "number" || item.valor_estimado > maximum)) return false;
    if (situation && item.situacao !== situation) return false;
    if (deadlineBefore && String(item.encerramento ?? "").slice(0, 10) > deadlineBefore) return false;
    return true;
  }).sort((left, right) => String(left.encerramento ?? "9999").localeCompare(String(right.encerramento ?? "9999")));
}

function render() {
  const items = filteredItems();
  const summary = `${items.length} oportunidade${items.length === 1 ? "" : "s"} encontrada${items.length === 1 ? "" : "s"}`;
  document.querySelector("#result-count").textContent = collectionStale ? `BASE DESATUALIZADA · ${summary}` : summary;
  const paginationWrap = document.querySelector("#pagination");
  const paginationInfo = document.querySelector("#pagination-info");
  const currentPageEl = document.querySelector("#current-page");
  const prevBtn = document.querySelector("#prev-page");
  const nextBtn = document.querySelector("#next-page");

  if (!collectionAvailable) {
    document.querySelector("#result-count").textContent = "Aguardando a primeira coleta bem-sucedida";
    list.innerHTML = '<tr><td colspan="5" class="empty-state">Ainda não há uma coleta concluída. Isso não significa que não existam oportunidades no PNCP.</td></tr>';
    if (paginationWrap) paginationWrap.hidden = true;
    return;
  }
  if (collectionStale) {
    document.querySelector("#result-count").textContent = "Snapshot desatualizado · oportunidades ocultas";
    list.innerHTML = '<tr><td colspan="5" class="empty-state">A coleta ultrapassou a validade configurada. Consulte as oportunidades diretamente no PNCP até uma nova atualização.</td></tr>';
    if (paginationWrap) paginationWrap.hidden = true;
    return;
  }
  if (!items.length) {
    list.innerHTML = '<tr><td colspan="5" class="empty-state">Nenhuma oportunidade corresponde aos filtros. Amplie a busca ou consulte o PNCP.</td></tr>';
    if (paginationWrap) paginationWrap.hidden = true;
    return;
  }

  const totalPages = Math.ceil(items.length / PAGE_SIZE) || 1;
  if (currentPage > totalPages) currentPage = totalPages;
  if (currentPage < 1) currentPage = 1;

  const startIndex = (currentPage - 1) * PAGE_SIZE;
  const endIndex = Math.min(startIndex + PAGE_SIZE, items.length);
  const pageItems = items.slice(startIndex, endIndex);

  list.innerHTML = pageItems.map((item) => {
    const slug = String(item.id ?? item.numero ?? "oportunidade").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    const detail = item.id ? `editais/${slug}.html` : "#";
    const link = typeof item.link === "string" && item.link.startsWith("https://pncp.gov.br/")
      ? `<a class="official-link" href="${escapeHTML(item.link)}" target="_blank" rel="noopener">PNCP ↗</a>`
      : "<span class=\"opp-meta\">Link indisponivel</span>";
    const location = [item.municipio, item.uf].filter(Boolean).map(escapeHTML).join(" / ") || "Nao informado";
    const isDispensa = normalizeText(item.modalidade ?? "").includes("dispensa");
    const isMeEpp = typeof item.valor_estimado === "number" && item.valor_estimado > 0 && item.valor_estimado <= 80000;
    const dispensaBadge = isDispensa ? '<span class="badge-pill badge-dispensa">⚡ Dispensa</span>' : '';
    const meeppBadge = isMeEpp ? '<span class="badge-pill badge-meepp">🛡️ Até 80k (ME/EPP)</span>' : '';
    const badges = (dispensaBadge || meeppBadge) ? `<div style="margin-bottom: 5px;">${dispensaBadge}${meeppBadge}</div>` : '';
    return `<tr><td>${badges}<a class="opp-title" href="${detail}">${escapeHTML(displayOr(item.objeto))}</a><span class="opp-org">${escapeHTML(displayOr(item.orgao))}</span><span class="opp-meta">${escapeHTML(displayOr(item.modalidade))} · ${escapeHTML(displayOr(item.numero))}</span></td><td class="opp-location">${location}</td><td>${escapeHTML(formatCurrency(item.valor_estimado))}</td><td class="deadline">${escapeHTML(formatDate(item.encerramento))}</td><td>${link}</td></tr>`;
  }).join("");

  if (paginationWrap) {
    paginationWrap.hidden = items.length <= PAGE_SIZE;
    paginationInfo.textContent = `Mostrando ${startIndex + 1}–${endIndex} de ${items.length} oportunidades`;
    currentPageEl.textContent = `Página ${currentPage} de ${totalPages}`;
    prevBtn.disabled = currentPage <= 1;
    nextBtn.disabled = currentPage >= totalPages;
  }
}

function renderDigest() {
  const preview = document.querySelector("#digest-preview");
  const item = [...opportunities].sort((a, b) => String(a.encerramento ?? "9999").localeCompare(String(b.encerramento ?? "9999")))[0];
  if (!item) {
    preview.innerHTML = collectionAvailable ? "<p>Nenhuma oportunidade aberta disponível na coleta atual.</p>" : "<p>Prévia indisponível até a primeira coleta bem-sucedida.</p>";
    return;
  }
  const link = typeof item.link === "string" && item.link.startsWith("https://pncp.gov.br/")
    ? `<p><a href="${escapeHTML(item.link)}" target="_blank" rel="noopener">Abrir oportunidade no PNCP ↗</a></p>` : "";
  preview.innerHTML = `<p><strong>${escapeHTML(displayOr(item.objeto))}</strong></p><p>${escapeHTML(displayOr(item.orgao))} · ${escapeHTML([item.municipio, item.uf].filter(Boolean).join(" / "))}</p><p>Prazo: ${escapeHTML(formatDate(item.encerramento))}<br>Estimado: ${escapeHTML(formatCurrency(item.valor_estimado))}</p>${link}`;
}

function updateLastCollection(value) {
  const formatted = formatDate(value);
  document.querySelector("#last-update").textContent = value ? `${formatted}${collectionStale ? " · desatualizada" : ""}` : "Sem coleta concluída";
  document.querySelector("#data-updated").textContent = formatted;
}

async function loadData() {
  try {
    const response = await fetch("data/opportunities.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    opportunities = Array.isArray(data.items) ? data.items : [];
    collectionAvailable = Boolean(data.last_successful_collection);
    const updatedAt = Date.parse(data.last_successful_collection ?? "");
    const maxAgeHours = Number(data.max_data_age_hours ?? 36);
    const ageMs = Date.now() - updatedAt;
    collectionStale = collectionAvailable && (!Number.isFinite(updatedAt) || ageMs < -300000 || ageMs > maxAgeHours * 3600000);
    const freshnessWarning = document.querySelector("#freshness-warning");
    if (collectionStale) {
      freshnessWarning.hidden = false;
      freshnessWarning.textContent = `Snapshot desatualizado. Última coleta: ${formatDate(data.last_successful_collection)}. Confirme prazo e situação no PNCP antes de agir.`;
      document.querySelector(".signal-top span").textContent = "BASE DESATUALIZADA";
    }
    document.querySelector("#hero-count").textContent = collectionAvailable && !collectionStale ? String(opportunities.length) : "—";
    updateLastCollection(data.last_successful_collection);
    const ufs = [...new Set(opportunities.map((item) => item.uf).filter(Boolean))].sort();
    for (const uf of ufs) {
      const option = document.createElement("option");
      option.value = uf;
      option.textContent = uf;
      ufSelect.append(option);
    }
    const modalities = [...new Set(opportunities.map((item) => item.modalidade).filter(Boolean))].sort();
    for (const mod of modalities) {
      const option = document.createElement("option");
      option.value = mod;
      option.textContent = mod;
      modalitySelect?.append(option);
    }
    const situations = [...new Set(opportunities.map((item) => item.situacao).filter(Boolean))].sort();
    for (const situation of situations) {
      const option = document.createElement("option");
      option.value = situation;
      option.textContent = situation;
      situationSelect.append(option);
    }
    const params = new URLSearchParams(location.search);
    keywordInput.value = params.get("keyword") ?? "";
    ufSelect.value = params.get("uf") ?? "";
    render();
    renderDigest();
  } catch (error) {
    document.querySelector("#hero-count").textContent = "—";
    document.querySelector("#last-update").textContent = "Fonte temporariamente indisponível";
    document.querySelector("#data-updated").textContent = "Não foi possível atualizar";
    document.querySelector("#result-count").textContent = "Falha ao carregar a coleta; não equivale a zero oportunidades.";
    list.innerHTML = '<tr><td colspan="5" class="empty-state">Os dados não puderam ser carregados. Tente novamente mais tarde ou consulte o PNCP.</td></tr>';
    document.querySelector("#digest-preview").textContent = "Prévia indisponível porque a coleta não foi carregada.";
    console.error("Falha ao ler dados do radar", error);
  }
}

function onFilterChange() {
  currentPage = 1;
  render();
}

document.querySelector("#filters").addEventListener("input", onFilterChange);
document.querySelector("#filters").addEventListener("change", onFilterChange);
document.querySelector("#filters").addEventListener("reset", () => requestAnimationFrame(onFilterChange));

document.querySelector("#prev-page")?.addEventListener("click", () => {
  if (currentPage > 1) {
    currentPage--;
    render();
    document.querySelector("#explorar")?.scrollIntoView({ behavior: "smooth" });
  }
});

document.querySelector("#next-page")?.addEventListener("click", () => {
  const totalPages = Math.ceil(filteredItems().length / PAGE_SIZE) || 1;
  if (currentPage < totalPages) {
    currentPage++;
    render();
    document.querySelector("#explorar")?.scrollIntoView({ behavior: "smooth" });
  }
});

loadData();

fetch("data/metrics.json", { cache: "no-store" }).then((response) => response.ok ? response.json() : null).then((metrics) => {
  if (!metrics) return;
  const metricsAge = Date.now() - Date.parse(metrics.as_of ?? "");
  const metricsStale = !Number.isFinite(metricsAge) || metricsAge < -300000 || metricsAge > Number(metrics.max_data_age_hours ?? 36) * 3600000;
  document.querySelector("#metric-open").textContent = metricsStale ? "Snapshot desatualizado" : String(metrics.open_opportunities ?? "—");
  document.querySelector("#metric-sent").textContent = metricsStale ? "Snapshot desatualizado" : String(metrics.telegram_messages_sent ?? 0);
  document.querySelector("#metric-leads").textContent = metrics.registrations === null ? "Consulte o Netlify" : String(metrics.registrations);
}).catch(() => {});