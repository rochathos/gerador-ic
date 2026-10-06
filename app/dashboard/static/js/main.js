/**
 * Productivity Assistant - JavaScript Utilities
 */

document.addEventListener("DOMContentLoaded", () => {
  initCommitsStore();
  setupColumnSelectors();
  setupQuickFilters();
  setupClipboardCopy();
  setupSearchForm();
  setupBranchAutocomplete();
});

/**
 * In-memory store for commit data on the current page
 */
window.COMMITS_STORE = {};

function initCommitsStore() {
  window.COMMITS_STORE = {};
  const el = document.getElementById("commits-data");
  if (!el) return;
  try {
    const list = JSON.parse(el.textContent);
    if (Array.isArray(list)) {
      list.forEach((c) => {
        if (c && c.hash) {
          window.COMMITS_STORE[c.hash] = c;
        }
      });
    }
  } catch (err) {
    console.error("Erro ao inicializar COMMITS_STORE:", err);
  }
}

/**
 * Configuration & Definition of Visible Columns in Commits Tables
 */
const COMMITS_COLUMNS_DEF = [
  { key: 'hash', label: 'Hash', icon: 'bi-hash', default: true },
  { key: 'date', label: 'Data / Hora', icon: 'bi-calendar3', default: true },
  { key: 'author', label: 'Autor', icon: 'bi-person', default: true },
  { key: 'repo', label: 'Repositório', icon: 'bi-folder2', default: true },
  { key: 'branch', label: 'Branch', icon: 'bi-diagram-2', default: true },
  { key: 'message', label: 'Mensagem do Commit', icon: 'bi-chat-left-text', default: true },
  { key: 'files', label: 'Arquivos / Ajustes', icon: 'bi-file-earmark-code', default: true },
  { key: 'status', label: 'Status IC', icon: 'bi-check-circle', default: true },
  { key: 'actions', label: 'Criar IC (Ação)', icon: 'bi-card-checklist', default: true },
];

const COLUMNS_STORAGE_KEY = 'gerador_ic_commits_table_columns_v1';

function getVisibleColumnsMap() {
  try {
    const saved = localStorage.getItem(COLUMNS_STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      if (typeof parsed === 'object' && parsed !== null) {
        return parsed;
      }
    }
  } catch (e) {
    console.warn('Erro ao ler colunas salvas:', e);
  }
  const defMap = {};
  COMMITS_COLUMNS_DEF.forEach(c => { defMap[c.key] = c.default; });
  return defMap;
}

function saveVisibleColumnsMap(colMap) {
  try {
    localStorage.setItem(COLUMNS_STORAGE_KEY, JSON.stringify(colMap));
  } catch (e) {
    console.warn('Erro ao salvar colunas:', e);
  }
}

function applyTableColumnVisibility() {
  const colMap = getVisibleColumnsMap();
  COMMITS_COLUMNS_DEF.forEach(c => {
    const isVisible = colMap[c.key] !== false;
    const cells = document.querySelectorAll(`table.table-custom th[data-col="${c.key}"], table.table-custom td[data-col="${c.key}"]`);
    cells.forEach(el => {
      if (isVisible) {
        el.classList.remove('col-hidden', 'd-none');
      } else {
        el.classList.add('col-hidden');
      }
    });

    const chks = document.querySelectorAll(`.column-toggle-check[data-col="${c.key}"]`);
    chks.forEach(chk => {
      chk.checked = isVisible;
    });
  });

  const total = COMMITS_COLUMNS_DEF.length;
  const activeCount = COMMITS_COLUMNS_DEF.filter(c => colMap[c.key] !== false).length;
  document.querySelectorAll(".col-count-badge").forEach(b => {
    b.textContent = `${activeCount}/${total}`;
  });
}

function toggleTableColumn(colKey, isChecked) {
  const colMap = getVisibleColumnsMap();
  colMap[colKey] = isChecked;
  saveVisibleColumnsMap(colMap);
  applyTableColumnVisibility();
}

function toggleAllTableColumns(visible) {
  const colMap = {};
  COMMITS_COLUMNS_DEF.forEach(c => {
    colMap[c.key] = visible;
  });
  saveVisibleColumnsMap(colMap);
  applyTableColumnVisibility();
}

function resetTableColumns() {
  try {
    localStorage.removeItem(COLUMNS_STORAGE_KEY);
  } catch (e) {}
  applyTableColumnVisibility();
}

function setupColumnSelectors() {
  const containers = document.querySelectorAll(".column-selector-list");
  if (!containers.length) return;

  const colMap = getVisibleColumnsMap();

  containers.forEach(container => {
    let html = "";
    COMMITS_COLUMNS_DEF.forEach(c => {
      const isChecked = colMap[c.key] !== false;
      const inputId = `col-toggle-${c.key}-${Math.random().toString(36).substring(2, 7)}`;
      html += `
        <div class="column-toggle-item d-flex align-items-center justify-content-between">
          <div class="form-check form-check-custom mb-0 d-flex align-items-center gap-2 w-100">
            <input class="form-check-input column-toggle-check" type="checkbox" id="${inputId}" data-col="${c.key}" ${isChecked ? "checked" : ""} onchange="toggleTableColumn('${c.key}', this.checked)">
            <label class="form-check-label text-light small user-select-none d-flex align-items-center gap-1 w-100" for="${inputId}">
              <i class="bi ${c.icon} text-primary me-1" style="font-size: 0.85rem;"></i>
              <span>${c.label}</span>
            </label>
          </div>
        </div>
      `;
    });
    container.innerHTML = html;
  });

  applyTableColumnVisibility();
}

/**
 * Open Create Catalog Item (IC) Modal by commit hash
 */
async function openCreateICByHash(commitHash, defaultNature = null) {
  if (!commitHash) return;
  if (!window.COMMITS_STORE || Object.keys(window.COMMITS_STORE).length === 0) {
    initCommitsStore();
  }
  let commit = window.COMMITS_STORE[commitHash];
  if (!commit) {
    const match = Object.values(window.COMMITS_STORE).find(
      (c) => (c.hash && c.hash.startsWith(commitHash)) || (c.short_hash && c.short_hash.startsWith(commitHash))
    );
    if (match) {
      commit = match;
    }
  }

  const hasXml = commit && (commit.has_xml_changes || commit.xml_files_count > 0 || (Array.isArray(commit.files_changed) && commit.files_changed.some(f => (typeof f === 'object' ? f.is_xml : String(f).toLowerCase().endsWith('.xml')))));
  const hasSql = commit && (commit.has_sql_changes || commit.sql_files_count > 0 || (Array.isArray(commit.files_changed) && commit.files_changed.some(f => (typeof f === 'object' ? f.is_sql : String(f).toLowerCase().endsWith('.sql')))));
  const needsInspect = !commit || ((hasXml || hasSql) && !commit.xml_analyzed);

  if (needsInspect) {
    const overlay = document.getElementById("loading-overlay");
    const overlaySub = document.getElementById("loading-overlay-subtitle");
    if (overlay) {
      if (overlaySub) overlaySub.textContent = "Analisando scripts SQL e tags XML do commit em tempo real...";
      overlay.classList.add("active");
    }

    try {
      const res = await fetch(`/api/commits/inspect/${encodeURIComponent(commitHash)}`);
      const data = await res.json();
      if (data.success && data.commit) {
        commit = data.commit;
        commit.xml_analyzed = true;
        window.COMMITS_STORE[commit.hash] = commit;
      }
    } catch (err) {
      console.error("Erro ao inspecionar commit:", err);
    } finally {
      if (overlay) {
        overlay.classList.remove("active");
      }
    }
  }

  if (commit) {
    openCreateICModal(commit, defaultNature);
  } else {
    alert(`Commit '${commitHash}' não encontrado no repositório.`);
  }
}

/**
 * Open Files Modal by commit hash
 */
async function viewFilesByHash(commitHash) {
  if (!commitHash) return;
  if (!window.COMMITS_STORE || Object.keys(window.COMMITS_STORE).length === 0) {
    initCommitsStore();
  }
  let commit = window.COMMITS_STORE[commitHash];
  if (!commit) {
    const match = Object.values(window.COMMITS_STORE).find(
      (c) => (c.hash && c.hash.startsWith(commitHash)) || (c.short_hash && c.short_hash.startsWith(commitHash))
    );
    if (match) {
      commit = match;
    }
  }

  const hasXml = commit && (commit.has_xml_changes || commit.xml_files_count > 0 || (Array.isArray(commit.files_changed) && commit.files_changed.some(f => (typeof f === 'object' ? f.is_xml : String(f).toLowerCase().endsWith('.xml')))));
  const needsInspect = !commit || (hasXml && !commit.xml_analyzed);

  if (needsInspect) {
    const overlay = document.getElementById("loading-overlay");
    const overlaySub = document.getElementById("loading-overlay-subtitle");
    if (overlay) {
      if (overlaySub) overlaySub.textContent = "Carregando arquivos e métricas do commit...";
      overlay.classList.add("active");
    }

    try {
      const res = await fetch(`/api/commits/inspect/${encodeURIComponent(commitHash)}`);
      const data = await res.json();
      if (data.success && data.commit) {
        commit = data.commit;
        commit.xml_analyzed = true;
        window.COMMITS_STORE[commit.hash] = commit;
      }
    } catch (err) {
      console.error("Erro ao inspecionar commit para arquivos:", err);
    } finally {
      if (overlay) {
        overlay.classList.remove("active");
      }
    }
  }

  if (commit && commit.files_changed) {
    viewFiles(commitHash, commit.files_changed, commit);
  } else {
    viewFiles(commitHash, [], commit);
  }
}

/**
 * Format Date to YYYY-MM-DDTHH:MM for datetime-local inputs
 */
function formatDatetimeLocal(date) {
  const pad = (n) => String(n).padStart(2, '0');
  const yyyy = date.getFullYear();
  const mm = pad(date.getMonth() + 1);
  const dd = pad(date.getDate());
  const hh = pad(date.getHours());
  const min = pad(date.getMinutes());
  return `${yyyy}-${mm}-${dd}T${hh}:${min}`;
}

/**
 * Quick date filter buttons logic
 */
function setupQuickFilters() {
  const filterBtns = document.querySelectorAll(".btn-quick-filter");
  const startDateInput = document.getElementById("start_date");
  const endDateInput = document.getElementById("end_date");

  if (!startDateInput || !endDateInput) return;

  filterBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      filterBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      const filter = btn.dataset.filter;
      const now = new Date();
      let start = new Date();
      let end = new Date();

      switch (filter) {
        case "hoje":
          start.setHours(0, 0, 0, 0);
          end.setHours(23, 59, 59, 999);
          break;

        case "ontem":
          start.setDate(now.getDate() - 1);
          start.setHours(0, 0, 0, 0);
          end.setDate(now.getDate() - 1);
          end.setHours(23, 59, 59, 999);
          break;

        case "esta_semana":
          // Monday as start of week
          const day = now.getDay();
          const diffToMonday = now.getDate() - day + (day === 0 ? -6 : 1);
          start = new Date(now.setDate(diffToMonday));
          start.setHours(0, 0, 0, 0);
          end = new Date();
          end.setHours(23, 59, 59, 999);
          break;

        case "este_mes":
          start = new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0);
          end = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59);
          break;

        case "personalizado":
        default:
          return;
      }

      startDateInput.value = formatDatetimeLocal(start);
      endDateInput.value = formatDatetimeLocal(end);
    });
  });
}

/**
 * Setup clipboard copy for commit hashes
 */
function setupClipboardCopy() {
  document.querySelectorAll(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const text = btn.dataset.copy;
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        const originalHtml = btn.innerHTML;
        btn.innerHTML = '<i class="bi bi-check2 text-success"></i>';
        setTimeout(() => {
          btn.innerHTML = originalHtml;
        }, 1500);
      } catch (err) {
        console.error("Falha ao copiar:", err);
      }
    });
  });
}

/**
 * Loading overlay handler on form submit
 */
function setupSearchForm() {
  const form = document.getElementById("search-form");
  const overlay = document.getElementById("loading-overlay");
  const subtitle = document.getElementById("loading-overlay-subtitle");

  if (form && overlay) {
    form.addEventListener("submit", () => {
      if (subtitle) {
        subtitle.textContent = "Consultando commits no Git em tempo real...";
      }
      overlay.classList.add("active");
    });
  }
}

/**
 * Open files changed modal
 */
function viewFiles(commitHash, filesJson, commitData) {
  const modalTitle = document.getElementById("filesModalTitle");
  const modalBody = document.getElementById("filesModalBody");
  if (!modalTitle || !modalBody) return;

  modalTitle.textContent = `Arquivos Alterados (${commitHash.substring(0, 7)})`;
  
  let files = [];
  try {
    files = typeof filesJson === "string" ? JSON.parse(filesJson) : filesJson;
  } catch (e) {
    files = [];
  }

  let commit = commitData || null;
  if (!commit && window.COMMITS_STORE) {
    commit = window.COMMITS_STORE[commitHash] || Object.values(window.COMMITS_STORE).find(
      (c) => (c.hash && c.hash.startsWith(commitHash)) || (c.short_hash && c.short_hash.startsWith(commitHash))
    ) || null;
  }

  const rawMetrics = (commit && commit.xml_tags_metrics) || {};
  const flows = rawMetrics.flows || null;
  const icTotalAdded = rawMetrics.total_added || 0;
  const icTotalRemoved = rawMetrics.total_removed || 0;
  const icTotalModified = rawMetrics.total_modified || 0;
  const icEffectiveTotal = (commit && commit.ic_count !== undefined)
    ? commit.ic_count
    : (rawMetrics.total_ics !== undefined ? rawMetrics.total_ics : (icTotalAdded + icTotalRemoved + icTotalModified));

  if (!files || files.length === 0) {
    modalBody.innerHTML = '<p class="text-muted">Nenhum arquivo listado ou alterado.</p>';
  } else {
    // Check if any XML files exist
    let xmlCount = 0;
    files.forEach(f => {
      const isXml = typeof f === "object" ? f.is_xml : String(f).toLowerCase().endsWith(".xml");
      if (isXml) xmlCount++;
    });

    let headerHtml = "";
    if (xmlCount > 0) {
      const partsBadges = [];
      if (icTotalAdded > 0) {
        partsBadges.push(`<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1">+${icTotalAdded} adições</span>`);
      }
      if (icTotalRemoved > 0) {
        partsBadges.push(`<span class="badge bg-danger-subtle text-danger border border-danger-subtle px-2 py-1">-${icTotalRemoved} remoções</span>`);
      }
      if (icTotalModified > 0) {
        partsBadges.push(`<span class="badge bg-warning-subtle text-warning border border-warning-subtle px-2 py-1">~${icTotalModified} ajustes</span>`);
      }
      const totalBadgeText = `${icEffectiveTotal} IC(s) no total`;
      partsBadges.push(`<span class="badge bg-warning text-dark fw-bold px-2 py-1">${totalBadgeText}</span>`);

      headerHtml = `
        <div class="card-glass p-3 mb-3 border-warning border-opacity-50 bg-warning bg-opacity-10 rounded-3">
          <div class="d-flex flex-wrap align-items-center justify-content-between gap-2">
            <div class="d-flex align-items-center gap-2">
              <i class="bi bi-filetype-xml fs-4 text-warning"></i>
              <div>
                <div class="fw-bold text-warning small">CONTAGEM PARA ICs (ARQUIVOS XML)</div>
                <div class="small text-light">${xmlCount} arquivo(s) XML alterado(s) neste commit</div>
              </div>
            </div>
            <div class="d-flex flex-wrap gap-2 align-items-center">
              ${partsBadges.join(" ")}
            </div>
          </div>
        </div>
      `;
    }

    let listHtml = headerHtml + '<ul class="list-group list-group-flush bg-transparent gap-2">';
    files.forEach(f => {
      const isObj = typeof f === "object";
      const filePath = isObj ? (f.path || f.filename) : String(f);
      const isXml = isObj ? f.is_xml : filePath.toLowerCase().endsWith(".xml");
      const ins = isObj ? (f.insertions || 0) : 0;
      const del = isObj ? (f.deletions || 0) : 0;
      const lines = isObj ? (f.lines || 0) : 0;

      let rightBadgesHtml = "";
      let tagPillsHtml = "";

      if (isXml && flows) {
        const flowData = findFlowMetricsForFile(filePath, flows);
        if (flowData) {
          const fAdded = flowData.added || {};
          const fRemoved = flowData.removed || {};
          const fModified = flowData.modified || {};
          const fTotAdd = flowData.total_added || Object.values(fAdded).reduce((a, b) => a + b, 0);
          const fTotRem = flowData.total_removed || Object.values(fRemoved).reduce((a, b) => a + b, 0);
          const fTotMod = flowData.total_modified || Object.values(fModified).reduce((a, b) => a + b, 0);
          const fTotalICs = flowData.total_ics !== undefined ? flowData.total_ics : (fTotAdd + fTotRem + fTotMod);

          const icBadges = [];
          if (fTotAdd > 0) {
            icBadges.push(`<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1" title="Tags Adicionadas">+${fTotAdd}</span>`);
          }
          if (fTotRem > 0) {
            icBadges.push(`<span class="badge bg-danger-subtle text-danger border border-danger-subtle px-2 py-1" title="Tags Removidas">-${fTotRem}</span>`);
          }
          if (fTotMod > 0) {
            icBadges.push(`<span class="badge bg-warning-subtle text-warning border border-warning-subtle px-2 py-1" title="Tags Ajustadas">~${fTotMod}</span>`);
          }
          icBadges.push(`<span class="badge bg-warning text-dark fw-bold px-2 py-1" title="Itens de Catálogo">${fTotalICs} IC(s)</span>`);

          if (ins > 0 || del > 0) {
            icBadges.push(`<span class="badge bg-dark text-muted border border-secondary border-opacity-50 px-2 py-1" title="Linhas Git: +${ins} / -${del} (${lines} linhas)">${lines} lin</span>`);
          }

          rightBadgesHtml = icBadges.join(" ");

          const pills = [];
          Object.entries(fAdded).forEach(([t, c]) => {
            pills.push(`<span class="badge bg-success bg-opacity-25 text-success border border-success-subtle py-0 px-1" style="font-size:0.65rem;" title="Adicionada">+&lt;${escapeHtml(t)}&gt;: ${c}</span>`);
          });
          Object.entries(fRemoved).forEach(([t, c]) => {
            pills.push(`<span class="badge bg-danger bg-opacity-25 text-danger border border-danger-subtle py-0 px-1" style="font-size:0.65rem;" title="Removida">-&lt;${escapeHtml(t)}&gt;: ${c}</span>`);
          });
          Object.entries(fModified).forEach(([t, c]) => {
            pills.push(`<span class="badge bg-warning bg-opacity-25 text-warning border border-warning-subtle py-0 px-1" style="font-size:0.65rem;" title="Ajustada / Modificada">~&lt;${escapeHtml(t)}&gt;: ${c}</span>`);
          });
          if (pills.length > 0) {
            tagPillsHtml = `<div class="d-flex align-items-center gap-1 flex-wrap mt-1">${pills.join(" ")}</div>`;
          }
        }
      }

      if (!rightBadgesHtml) {
        if (isObj && (ins > 0 || del > 0 || lines > 0)) {
          rightBadgesHtml = `
            <span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1" title="Linhas inseridas">+${ins}</span>
            <span class="badge bg-danger-subtle text-danger border border-danger-subtle px-2 py-1" title="Linhas deletadas">-${del}</span>
            <span class="badge bg-secondary-subtle text-light border border-secondary px-2 py-1" title="Total de edições">${lines} edições</span>
          `;
        } else {
          rightBadgesHtml = '<span class="text-muted small">Modificado</span>';
        }
      }

      listHtml += `
        <li class="list-group-item bg-dark bg-opacity-50 rounded-2 border ${isXml ? 'border-warning border-opacity-50' : 'border-secondary border-opacity-25'} p-2 d-flex flex-wrap align-items-center justify-content-between gap-2">
          <div class="d-flex flex-column text-truncate" style="max-width: 65%;">
            <div class="d-flex align-items-center gap-2 text-truncate">
              ${isXml ? '<span class="badge bg-warning text-dark fw-bold" style="font-size:0.7rem;"><i class="bi bi-filetype-xml"></i> XML</span>' : '<i class="bi bi-file-earmark-code text-info"></i>'}
              ${isObj && f.is_rename ? `<span class="badge bg-info-subtle text-info border border-info-subtle" style="font-size:0.68rem;" title="Renomeado de: ${escapeHtml(f.old_path || '')}"><i class="bi bi-arrow-repeat me-1"></i>Renomeado</span>` : ''}
              <span class="font-monospace small ${isXml ? 'text-warning fw-semibold' : 'text-light'} text-truncate" title="${filePath}">${filePath}</span>
            </div>
            ${tagPillsHtml}
          </div>
          <div class="d-flex align-items-center gap-1 font-monospace" style="font-size: 0.8rem;">
            ${rightBadgesHtml}
          </div>
        </li>
      `;
    });
    listHtml += '</ul>';
    modalBody.innerHTML = listHtml;
  }

  const modalEl = document.getElementById("filesModal");
  if (modalEl) {
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
  }
}

function decodeGitPath(path) {
  if (!path) return "";
  let clean = String(path).replace(/^["']|["']$/g, "");
  if (clean.includes("\\")) {
    try {
      clean = clean.replace(/\\([0-7]{3})/g, (match, octal) => String.fromCharCode(parseInt(octal, 8)));
      clean = decodeURIComponent(escape(clean));
    } catch (e) {}
  }
  return clean;
}

function findFlowMetricsForFile(path, flows) {
  if (!flows || !path) return null;
  if (flows[path]) return flows[path];
  const pNorm = path.replace(/\\/g, "/").trim().toLowerCase();
  for (const [fPath, fData] of Object.entries(flows)) {
    if (fPath.replace(/\\/g, "/").trim().toLowerCase() === pNorm) return fData;
  }
  const base = pNorm.split("/").pop();
  for (const [fPath, fData] of Object.entries(flows)) {
    if (fPath.replace(/\\/g, "/").trim().toLowerCase().split("/").pop() === base) return fData;
  }
  return null;
}

/**
 * Global variable for modal commit state
 */
let currentModalCommit = null;

/**
 * Open Create Catalog Item (IC) Modal for a specific commit
 */
window.currentICNature = 'fluxo'; // 'fluxo' | 'sql'

/**
 * Switch the active nature in the Create IC modal ('fluxo' vs 'sql')
 */
function switchICNature(natureza) {
  if (!currentModalCommit) return;
  const descEl = document.getElementById("icInputDesc");
  if (descEl) {
    if (window.currentICNature === 'sql') {
      currentModalCommit._edited_desc_sql = descEl.value;
    } else {
      currentModalCommit._edited_desc_fluxo = descEl.value;
    }
  }
  window.currentICNature = (natureza === 'sql') ? 'sql' : 'fluxo';
  renderModalForCurrentNature();
}

/**
 * Update the tab badges and status tags inside the modal
 */
function updateNatureTabBadges(commit) {
  const badgeFluxoCount = document.getElementById("badgeNatureFluxoCount");
  const badgeFluxoStatus = document.getElementById("badgeNatureFluxoStatus");
  const badgeSqlCount = document.getElementById("badgeNatureSqlCount");
  const badgeSqlStatus = document.getElementById("badgeNatureSqlStatus");

  const hasXml = commit.has_xml_changes || commit.xml_files_count > 0;
  const hasSql = commit.has_sql_changes || commit.sql_files_count > 0;

  const countXml = (commit.ic_count_xml && commit.ic_count_xml > 0) ? commit.ic_count_xml : (hasXml ? (commit.ic_count || commit.xml_files_count || 1) : 0);
  const countSql = (commit.ic_count_sql && commit.ic_count_sql > 0) ? commit.ic_count_sql : (hasSql ? (commit.sql_files_count || 1) : 0);

  if (badgeFluxoCount) badgeFluxoCount.textContent = `${countXml} ICs`;
  if (badgeSqlCount) badgeSqlCount.textContent = `${countSql} ICs`;

  if (badgeFluxoStatus) {
    if (commit.redmine_id_fluxo) {
      badgeFluxoStatus.className = "badge bg-warning text-dark fw-bold ms-1";
      badgeFluxoStatus.style.backgroundColor = "";
      badgeFluxoStatus.textContent = `#${commit.redmine_id_fluxo}`;
    } else if (commit.is_saved_fluxo) {
      badgeFluxoStatus.className = "badge bg-warning-subtle text-warning-emphasis border border-warning-subtle ms-1";
      badgeFluxoStatus.style.backgroundColor = "";
      badgeFluxoStatus.textContent = "Salvo";
    } else {
      badgeFluxoStatus.className = "badge bg-secondary ms-1 d-none";
      badgeFluxoStatus.style.backgroundColor = "";
    }
  }

  if (badgeSqlStatus) {
    if (commit.redmine_id_sql) {
      badgeSqlStatus.className = "badge text-dark fw-bold ms-1";
      badgeSqlStatus.style.backgroundColor = "#22d3ee";
      badgeSqlStatus.textContent = `#${commit.redmine_id_sql}`;
    } else if (commit.is_saved_sql) {
      badgeSqlStatus.className = "badge text-info border border-info-subtle ms-1";
      badgeSqlStatus.style.backgroundColor = "rgba(34, 211, 238, 0.15)";
      badgeSqlStatus.textContent = "Salvo";
    } else {
      badgeSqlStatus.className = "badge bg-secondary ms-1 d-none";
      badgeSqlStatus.style.backgroundColor = "";
    }
  }
}

/**
 * Render XML tags breakdown for Fluxo nature
 */
function renderXmlTagsDetail(commit, tagsAlert, countText, tagsDetail) {
  const rawMetrics = commit.xml_tags_metrics || {};
  let addedTags = {};
  let removedTags = {};
  let modifiedTags = {};
  let totalAdded = 0;
  let totalRemoved = 0;
  let totalModified = 0;
  const flows = rawMetrics.flows || null;

  if (rawMetrics.added !== undefined || rawMetrics.removed !== undefined || rawMetrics.modified !== undefined) {
    addedTags = rawMetrics.added || {};
    removedTags = rawMetrics.removed || {};
    modifiedTags = rawMetrics.modified || {};
    totalAdded = rawMetrics.total_added !== undefined ? rawMetrics.total_added : Object.values(addedTags).reduce((a, b) => a + b, 0);
    totalRemoved = rawMetrics.total_removed !== undefined ? rawMetrics.total_removed : Object.values(removedTags).reduce((a, b) => a + b, 0);
    totalModified = rawMetrics.total_modified !== undefined ? rawMetrics.total_modified : Object.values(modifiedTags).reduce((a, b) => a + b, 0);
  } else if (typeof rawMetrics === "object") {
    addedTags = rawMetrics;
    totalAdded = Object.values(addedTags).reduce((a, b) => a + b, 0);
  }

  const effectiveTotalICs = commit.ic_count_xml !== undefined ? commit.ic_count_xml : (commit.ic_count || (totalAdded + totalRemoved + totalModified));

  if (effectiveTotalICs > 0) {
    tagsAlert.classList.remove("d-none");
    let countLabel = `${effectiveTotalICs} Item(ns) de Catálogo (Fluxo XML) calculados`;
    const parts = [];
    if (totalAdded > 0) parts.push(`+${totalAdded} adições`);
    if (totalRemoved > 0) parts.push(`-${totalRemoved} remoções`);
    if (totalModified > 0) parts.push(`~${totalModified} ajustes`);
    if (parts.length > 0) {
      countLabel += ` (${parts.join(", ")})`;
    }
    countText.textContent = countLabel;

    const flowEntriesMap = new Map();
    if (commit.files_changed && Array.isArray(commit.files_changed)) {
      commit.files_changed.forEach(f => {
        const isObj = typeof f === "object";
        const rawPath = isObj ? (f.path || f.filename) : String(f);
        const path = decodeGitPath(rawPath);
        const isXml = isObj ? f.is_xml : path.toLowerCase().endsWith(".xml");
        if (isXml) {
          const flowData = findFlowMetricsForFile(path, flows);
          flowEntriesMap.set(path.replace(/\\/g, "/").toLowerCase(), {
            path: path,
            flowData: flowData
          });
        }
      });
    }

    if (flows && typeof flows === "object") {
      Object.entries(flows).forEach(([flowPath, flowData]) => {
        const key = flowPath.replace(/\\/g, "/").toLowerCase();
        const base = key.split("/").pop();
        let matchedKey = null;
        for (const existingKey of flowEntriesMap.keys()) {
          if (existingKey === key || existingKey.split("/").pop() === base) {
            matchedKey = existingKey;
            break;
          }
        }
        if (matchedKey) {
          const item = flowEntriesMap.get(matchedKey);
          if (!item.flowData) item.flowData = flowData;
        } else {
          flowEntriesMap.set(key, {
            path: flowPath,
            flowData: flowData
          });
        }
      });
    }

    let htmlBadges = "";
    if (flowEntriesMap.size > 0) {
      flowEntriesMap.forEach(({ path: flowPath, flowData }) => {
        const fAdded = (flowData && flowData.added) || {};
        const fRemoved = (flowData && flowData.removed) || {};
        const fModified = (flowData && flowData.modified) || {};
        const fTotalAdded = (flowData && flowData.total_added) || Object.values(fAdded).reduce((a, b) => a + b, 0);
        const fTotalRemoved = (flowData && flowData.total_removed) || Object.values(fRemoved).reduce((a, b) => a + b, 0);
        const fTotalModified = (flowData && flowData.total_modified) || Object.values(fModified).reduce((a, b) => a + b, 0);
        const fTotal = (flowData && flowData.total_ics !== undefined) ? flowData.total_ics : (fTotalAdded + fTotalRemoved + fTotalModified);

        htmlBadges += `<div class="p-2 mb-2 rounded bg-dark bg-opacity-50 border border-secondary border-opacity-25 w-100">`;
        const badgeClass = fTotal > 0 ? "bg-warning text-dark" : "bg-secondary text-light";
        const badgeText = fTotal > 0 ? `${fTotal} ICs` : "0 ICs (Sem tags de catálogo)";
        htmlBadges += `<div class="fw-semibold text-warning small mb-1 d-flex align-items-center justify-content-between"><span><i class="bi bi-file-earmark-code me-1"></i>Fluxo: <span class="text-light">${escapeHtml(flowPath)}</span></span><span class="badge ${badgeClass} fw-bold">${badgeText}</span></div>`;

        const fAddEntries = Object.entries(fAdded).sort((a, b) => b[1] - a[1]);
        const fRemEntries = Object.entries(fRemoved).sort((a, b) => b[1] - a[1]);
        const fModEntries = Object.entries(fModified).sort((a, b) => b[1] - a[1]);

        const tagBadges = [];
        if (fAddEntries.length > 0) {
          fAddEntries.forEach(([t, c]) => {
            tagBadges.push(`<span class="badge bg-success bg-opacity-25 text-success border border-success-subtle fw-semibold px-2 py-1" title="Adicionada"><i class="bi bi-plus-lg me-1"></i>&lt;${escapeHtml(t)}&gt;: ${c}</span>`);
          });
        }
        if (fRemEntries.length > 0) {
          fRemEntries.forEach(([t, c]) => {
            tagBadges.push(`<span class="badge bg-danger bg-opacity-25 text-danger border border-danger-subtle fw-semibold px-2 py-1" title="Removida"><i class="bi bi-dash-lg me-1"></i>&lt;${escapeHtml(t)}&gt;: ${c}</span>`);
          });
        }
        if (fModEntries.length > 0) {
          fModEntries.forEach(([t, c]) => {
            tagBadges.push(`<span class="badge bg-warning bg-opacity-25 text-warning border border-warning-subtle fw-semibold px-2 py-1" title="Ajustada / Modificada"><i class="bi bi-pencil-fill me-1" style="font-size:0.65rem;"></i>&lt;${escapeHtml(t)}&gt;: ${c}</span>`);
          });
        }

        if (tagBadges.length > 0) {
          htmlBadges += `<div class="d-flex align-items-center gap-1 flex-wrap">${tagBadges.join(" ")}</div>`;
        } else if (fTotal === 0) {
          htmlBadges += `<div class="text-muted small ps-1">Arquivo XML editado sem alteração direta em nós/transições/regras de catálogo.</div>`;
        }
        htmlBadges += `</div>`;
      });
    } else {
      const addEntries = Object.entries(addedTags).sort((a, b) => b[1] - a[1]);
      const remEntries = Object.entries(removedTags).sort((a, b) => b[1] - a[1]);
      const modEntries = Object.entries(modifiedTags).sort((a, b) => b[1] - a[1]);

      const tagBadges = [];
      if (addEntries.length > 0) {
        addEntries.forEach(([t, c]) => {
          tagBadges.push(`<span class="badge bg-success bg-opacity-25 text-success border border-success-subtle fw-semibold px-2 py-1" title="Adicionada"><i class="bi bi-plus-lg me-1"></i>&lt;${escapeHtml(t)}&gt;: ${c}</span>`);
        });
      }
      if (remEntries.length > 0) {
        remEntries.forEach(([t, c]) => {
          tagBadges.push(`<span class="badge bg-danger bg-opacity-25 text-danger border border-danger-subtle fw-semibold px-2 py-1" title="Removida"><i class="bi bi-dash-lg me-1"></i>&lt;${escapeHtml(t)}&gt;: ${c}</span>`);
        });
      }
      if (modEntries.length > 0) {
        modEntries.forEach(([t, c]) => {
          tagBadges.push(`<span class="badge bg-warning bg-opacity-25 text-warning border border-warning-subtle fw-semibold px-2 py-1" title="Ajustada / Modificada"><i class="bi bi-pencil-fill me-1" style="font-size:0.65rem;"></i>&lt;${escapeHtml(t)}&gt;: ${c}</span>`);
        });
      }

      if (tagBadges.length > 0) {
        htmlBadges = `<div class="d-flex align-items-center gap-1 flex-wrap">${tagBadges.join(" ")}</div>`;
      }
    }

    tagsDetail.innerHTML = htmlBadges || `<span class="text-muted small">Tags válidas calculadas.</span>`;
  } else {
    tagsAlert.classList.add("d-none");
    countText.textContent = "";
    tagsDetail.innerHTML = "";
  }
}

/**
 * Render the modal contents dynamically according to window.currentICNature ('fluxo' vs 'sql')
 */
function renderModalForCurrentNature() {
  const commit = currentModalCommit;
  if (!commit) return;

  const btnFluxo = document.getElementById("btnSelectIcFluxo");
  const btnSql = document.getElementById("btnSelectIcSql");
  const inputNatureza = document.getElementById("icInputNatureza");
  const inputActivity = document.getElementById("icInputActivityType");
  const displayActivity = document.getElementById("icDisplayActivityType");
  const natureBadge = document.getElementById("icNatureBadge");
  const descEl = document.getElementById("icInputDesc");
  const quantityEl = document.getElementById("icInputQuantity");
  const redmineBtn = document.getElementById("btnCreateICInRedmine");
  const simBtn = document.getElementById("btnSimulateICInRedmine");
  const redmineIdEl = document.getElementById("icInputRedmineId");
  const tagsAlert = document.getElementById("icTagsAlert");
  const countText = document.getElementById("icCountText");
  const tagsDetail = document.getElementById("icTagsDetail");
  const rulesBadge = document.getElementById("icRulesBadge");
  const subtitleEl = document.getElementById("icBreakdownSubtitle");

  const isSql = window.currentICNature === 'sql';

  // Toggle button styling for active nature
  if (btnFluxo && btnSql) {
    if (isSql) {
      btnFluxo.className = "btn btn-outline-warning flex-fill fw-bold d-flex align-items-center justify-content-center gap-2 py-2";
      btnSql.className = "btn flex-fill fw-bold d-flex align-items-center justify-content-center gap-2 py-2 shadow-sm text-dark";
      btnSql.style.backgroundColor = "#22d3ee";
    } else {
      btnFluxo.className = "btn btn-warning text-dark flex-fill fw-bold d-flex align-items-center justify-content-center gap-2 py-2 shadow-sm";
      btnSql.className = "btn btn-outline-info flex-fill fw-bold d-flex align-items-center justify-content-center gap-2 py-2";
      btnSql.style.backgroundColor = "";
    }
  }

  // Activity strings per nature
  const actFluxo = "Desenvolvimento - Criar/Manter tarefa de automação";
  const actSql = "Desenvolvimento - Criar/Manter scripts para extração de dados do banco de dados";
  if (inputNatureza) inputNatureza.value = isSql ? "sql" : "fluxo";
  if (inputActivity) inputActivity.value = isSql ? actSql : actFluxo;
  if (displayActivity) displayActivity.textContent = isSql ? actSql : actFluxo;

  if (natureBadge) {
    if (isSql) {
      natureBadge.className = "badge text-dark fw-bold";
      natureBadge.style.backgroundColor = "#22d3ee";
      natureBadge.textContent = "BANCO DE DADOS (SQL)";
    } else {
      natureBadge.className = "badge bg-warning text-dark fw-bold";
      natureBadge.style.backgroundColor = "";
      natureBadge.textContent = "CATÁLOGO / FLUXO (XML)";
    }
  }

  // Determine Redmine ID for this nature
  let currentRedmineId = isSql ? commit.redmine_id_sql : commit.redmine_id_fluxo;
  if (!currentRedmineId && !commit.tem_ambos_ajustes) {
    currentRedmineId = commit.redmine_id;
  }
  if (redmineIdEl) redmineIdEl.value = currentRedmineId || "";

  const hasXml = commit.has_xml_changes || commit.xml_files_count > 0;
  const hasSql = commit.has_sql_changes || commit.sql_files_count > 0;
  const hasBoth = commit.tem_ambos_ajustes || (hasXml && hasSql);
  const bothCreated = hasBoth && commit.redmine_id_fluxo && commit.redmine_id_sql;
  const singleCreated = !hasBoth && (commit.redmine_id || (isSql ? commit.redmine_id_sql : commit.redmine_id_fluxo));

  // Redmine button state: always a single unified button
  if (redmineBtn) {
    if (bothCreated) {
      redmineBtn.className = "btn btn-success d-flex align-items-center gap-1";
      redmineBtn.style.backgroundColor = "";
      redmineBtn.innerHTML = `<i class="bi bi-box-arrow-up-right"></i> Redmines #${commit.redmine_id_fluxo} e #${commit.redmine_id_sql}`;
      redmineBtn.disabled = false;
      redmineBtn.onclick = () => window.open(`https://redmine.tjce.jus.br/issues/${commit.redmine_id_fluxo}`, '_blank');
    } else if (singleCreated) {
      const singleId = commit.redmine_id || (isSql ? commit.redmine_id_sql : commit.redmine_id_fluxo);
      redmineBtn.className = "btn btn-success d-flex align-items-center gap-1";
      redmineBtn.style.backgroundColor = "";
      redmineBtn.innerHTML = `<i class="bi bi-box-arrow-up-right"></i> Redmine #${singleId}`;
      redmineBtn.disabled = false;
      redmineBtn.onclick = () => window.open(`https://redmine.tjce.jus.br/issues/${singleId}`, '_blank');
    } else {
      redmineBtn.className = "btn btn-warning text-dark fw-bold d-flex align-items-center gap-1";
      redmineBtn.style.backgroundColor = "";
      redmineBtn.innerHTML = '<i class="bi bi-cloud-arrow-up-fill"></i> Criar no Redmine';
      redmineBtn.disabled = false;
      redmineBtn.onclick = function() { createICDirectlyInRedmine(this, false); };
    }
  }

  // Simulation button label: always a single unified button
  if (simBtn) {
    simBtn.disabled = false;
    simBtn.className = "btn btn-outline-warning d-flex align-items-center gap-1";
    simBtn.innerHTML = '<i class="bi bi-shield-check"></i> Testar no Redmine (Simulação)';
  }

  // Quantity and Description for this nature
  if (isSql) {
    const sqlIcs = (commit.ic_count_sql && commit.ic_count_sql > 0) ? commit.ic_count_sql : (commit.has_sql_changes ? 1 : 1);
    if (quantityEl) quantityEl.value = sqlIcs > 0 ? sqlIcs : 1;
    if (descEl) descEl.value = commit._edited_desc_sql || commit.ic_description_sql || commit.ic_description || "";

    if (tagsAlert && countText && tagsDetail && rulesBadge && subtitleEl) {
      tagsAlert.classList.remove("d-none");
      rulesBadge.textContent = "Scripts SQL (Banco de Dados)";
      rulesBadge.className = "badge text-dark fw-bold";
      rulesBadge.style.backgroundColor = "#22d3ee";
      subtitleEl.textContent = "Casos de Uso e Operações DML/DDL identificados nos scripts .sql:";

      const sqlMetrics = commit.sql_scripts_metrics || {};
      const scripts = sqlMetrics.scripts || [];
      const totalIcs = sqlMetrics.total_ics || sqlIcs;
      countText.textContent = `${totalIcs} IC(s) de Banco de Dados calculados`;

      let html = "";
      if (scripts.length > 0) {
        scripts.forEach((sc) => {
          html += `<div class="p-2 mb-2 rounded bg-dark bg-opacity-50 border border-secondary border-opacity-25 w-100">`;
          html += `<div class="fw-semibold text-info small mb-1 d-flex align-items-center justify-content-between"><span><i class="bi bi-filetype-sql me-1"></i>Script: <span class="text-light">${escapeHtml(sc.nome_arquivo || "")}</span></span><span class="badge text-dark fw-bold" style="background:#22d3ee;">${sc.total_ics || 1} ICs</span></div>`;
          const casos = sc.casos_de_uso || [];
          if (casos.length > 0) {
            html += `<div class="mb-1 text-light small"><span class="text-muted small">Casos de Uso:</span></div>`;
            html += `<div class="d-flex flex-wrap gap-1 mb-1">`;
            casos.forEach(c => {
              html += `<span class="badge bg-info bg-opacity-25 text-info border border-info-subtle fw-semibold px-2 py-1"><i class="bi bi-check2 me-1"></i>${escapeHtml(c)}</span>`;
            });
            html += `</div>`;
          }
          const ops = sc.operacoes || {};
          const opBadges = [];
          for (const [op, cnt] of Object.entries(ops)) {
            if (cnt > 0) {
              opBadges.push(`<span class="badge bg-secondary-subtle text-light border border-secondary-subtle small">${escapeHtml(op)}: ${cnt}</span>`);
            }
          }
          if (opBadges.length > 0) {
            html += `<div class="d-flex flex-wrap gap-1 mt-1">${opBadges.join(" ")}</div>`;
          }
          html += `</div>`;
        });
      } else {
        html = `<div class="p-2 rounded bg-dark bg-opacity-50 border border-secondary border-opacity-25"><span class="badge text-dark fw-bold" style="background:#22d3ee;"><i class="bi bi-database me-1"></i>Ajuste em scripts SQL detectado</span></div>`;
      }
      tagsDetail.innerHTML = html;
    }
  } else {
    // Fluxo XML
    const xmlIcs = (commit.ic_count_xml && commit.ic_count_xml > 0) ? commit.ic_count_xml : ((commit.ic_count && commit.ic_count > 0) ? commit.ic_count : (commit.xml_files_count || 1));
    if (quantityEl) quantityEl.value = xmlIcs > 0 ? xmlIcs : 1;
    if (descEl) descEl.value = commit._edited_desc_fluxo || commit.ic_description_fluxo || commit.ic_description || "";

    if (tagsAlert && countText && tagsDetail && rulesBadge && subtitleEl) {
      rulesBadge.textContent = "Regras do Catálogo (PJE)";
      rulesBadge.className = "badge bg-warning text-dark fw-bold";
      rulesBadge.style.backgroundColor = "";
      subtitleEl.textContent = "Detalhamento das tags XML calculadas (Adições / Remoções - excluindo estruturais):";

      renderXmlTagsDetail(commit, tagsAlert, countText, tagsDetail);
    }
  }
}

/**
 * Open Create IC Modal for a commit, optionally preselecting 'fluxo' or 'sql'
 */
function openCreateICModal(commitData, defaultNature = null) {
  let commit = commitData;
  if (typeof commit === "string") {
    if (window.COMMITS_STORE && window.COMMITS_STORE[commit]) {
      commit = window.COMMITS_STORE[commit];
    } else {
      try {
        commit = JSON.parse(commitData);
      } catch (e) {
        console.error("Erro ao converter dados do commit:", e);
        return;
      }
    }
  }

  currentModalCommit = commit;

  const modalEl = document.getElementById("createICModal");
  if (!modalEl) return;

  const badgeEl = document.getElementById("icCommitBadge");
  const titleEl = document.getElementById("icInputTitle");
  const alertEl = document.getElementById("icFeedbackAlert");
  const alertText = document.getElementById("icFeedbackText");
  const dualAlert = document.getElementById("icDualNatureAlert");
  const branchBadgeEl = document.getElementById("icBranchBadge");

  // Reset feedback alert
  if (alertEl) {
    alertEl.classList.add("d-none");
    alertEl.classList.remove("alert-danger");
    alertEl.classList.add("alert-success");
  }
  if (alertText) {
    alertText.textContent = "";
  }

  // Reset logs container
  const redmineLogsCont = document.getElementById("icRedmineLogsContainer");
  const redmineLogsList = document.getElementById("icRedmineLogsList");
  const redmineLogsStatus = document.getElementById("icRedmineLogsStatus");
  if (redmineLogsCont) redmineLogsCont.classList.add("d-none");
  if (redmineLogsList) redmineLogsList.innerHTML = "";
  if (redmineLogsStatus) {
    redmineLogsStatus.className = "badge bg-secondary";
    redmineLogsStatus.textContent = "Aguardando";
  }

  // Populate badge & branch
  const shortHash = commit.short_hash || (commit.hash ? commit.hash.substring(0, 7) : "");
  if (badgeEl) {
    badgeEl.textContent = `Commit ${shortHash}`;
  }
  if (branchBadgeEl) {
    if (commit.branch) {
      branchBadgeEl.innerHTML = `<i class="bi bi-diagram-2 me-1"></i>${escapeHtml(commit.branch)}`;
      branchBadgeEl.classList.remove("d-none");
    } else {
      branchBadgeEl.classList.add("d-none");
    }
  }

  // Populate title
  let icTitle = commit.ic_title;
  if (!icTitle && commit.message) {
    icTitle = commit.message.split("\n")[0].trim().substring(0, 180);
  }
  if (titleEl) {
    titleEl.value = icTitle || "Atividade de Desenvolvimento";
    titleEl.oninput = onICInputChanged;
  }

  // Populate Complexity
  const complexityEl = document.getElementById("icInputComplexity");
  if (complexityEl) {
    complexityEl.value = commit.complexity || "Baixa";
  }

  // Check Dual Nature (XML and SQL simultaneously)
  const hasXml = commit.has_xml_changes || commit.xml_files_count > 0;
  const hasSql = commit.has_sql_changes || commit.sql_files_count > 0;
  const hasBoth = commit.tem_ambos_ajustes || (hasXml && hasSql);

  if (dualAlert) {
    if (hasBoth) {
      dualAlert.classList.remove("d-none");
    } else {
      dualAlert.classList.add("d-none");
    }
  }

  const natureSelectorCont = document.getElementById("icNatureSelectorContainer");
  if (natureSelectorCont) {
    if (hasBoth) {
      natureSelectorCont.classList.remove("d-none");
    } else {
      natureSelectorCont.classList.add("d-none");
    }
  }

  // Choose starting nature
  if (defaultNature) {
    window.currentICNature = defaultNature;
  } else if (hasSql && !hasXml) {
    window.currentICNature = 'sql';
  } else {
    window.currentICNature = 'fluxo';
  }

  // Update tabs badges & render modal for starting nature
  updateNatureTabBadges(commit);
  renderModalForCurrentNature();

  const modal = new bootstrap.Modal(modalEl);
  modal.show();
}

/**
 * Copy individual modal field (Title or Description) to clipboard
 */
async function copyModalField(fieldId, btn) {
  const field = document.getElementById(fieldId);
  if (!field) return;

  try {
    await navigator.clipboard.writeText(field.value);
    const origHtml = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-check2 text-success"></i> Copiado!';
    setTimeout(() => {
      btn.innerHTML = origHtml;
    }, 1500);
  } catch (err) {
    console.error("Erro ao copiar campo:", err);
  }
}

/**
 * Copy full IC format (Title + Description) directly for Redmine
 */
async function copyFullICToRedmine(btn) {
  const titleEl = document.getElementById("icInputTitle");
  const descEl = document.getElementById("icInputDesc");
  const alertEl = document.getElementById("icFeedbackAlert");
  const alertText = document.getElementById("icFeedbackText");

  const title = titleEl ? titleEl.value.trim() : "";
  const desc = descEl ? descEl.value.trim() : "";

  const commit = currentModalCommit;
  const hasXml = commit ? (commit.has_xml_changes || commit.xml_files_count > 0) : false;
  const hasSql = commit ? (commit.has_sql_changes || commit.sql_files_count > 0) : false;
  const hasBoth = commit && (commit.tem_ambos_ajustes || (hasXml && hasSql));

  let fullText = "";
  if (hasBoth) {
    const descFluxo = commit._edited_desc_fluxo || (window.currentICNature === 'fluxo' ? desc : commit.ic_description_fluxo) || desc;
    const descSql = commit._edited_desc_sql || (window.currentICNature === 'sql' ? desc : commit.ic_description_sql) || desc;
    fullText = `=== 1. TAREFA REDMINE: CATÁLOGO DA FUNCIONALIDADE (FLUXO XML) ===\nAtividade: Desenvolvimento - Criar/Manter tarefa de automação\nTítulo: ${title}\n\nDescrição:\n${descFluxo}\n\n=======================================================\n=== 2. TAREFA REDMINE: BANCO DE DADOS (SCRIPTS SQL) ===\nAtividade: Desenvolvimento - Criar/Manter scripts para extração de dados do banco de dados\nTítulo: ${title}\n\nDescrição:\n${descSql}`;
  } else {
    fullText = `TÍTULO:\n${title}\n\nDESCRIÇÃO:\n${desc}`;
  }

  try {
    await navigator.clipboard.writeText(fullText);
    if (btn) {
      const origHtml = btn.innerHTML;
      btn.innerHTML = '<i class="bi bi-check2 text-white"></i> Copiado!';
      setTimeout(() => {
        btn.innerHTML = origHtml;
      }, 1800);
    }
    if (alertEl && alertText) {
      alertEl.classList.remove("d-none", "alert-danger");
      alertEl.classList.add("alert-success");
      alertText.textContent = hasBoth 
        ? "Títulos e descrições dos 2 Redmines copiados com sucesso!" 
        : "Título e descrição copiados com sucesso! Cole diretamente no Redmine.";
    }
  } catch (err) {
    console.error("Erro ao copiar IC completo:", err);
  }
}

/**
 * Update the status badge in the commits table
 */
/**
 * Update the status badge in the commits table (supports dual Redmines)
 */
function updateTableStatusCell(commit) {
  if (!commit || !commit.hash) return;
  const cleanHash = commit.hash.trim().toLowerCase();
  let cell = document.getElementById(`status-cell-${commit.hash}`) || document.getElementById(`status-cell-${cleanHash}`);
  if (!cell && cleanHash.length >= 7) {
    cell = document.getElementById(`status-cell-${cleanHash.substring(0, 7)}`);
  }
  if (!cell) {
    const allCells = document.querySelectorAll('[id^="status-cell-"]');
    for (const c of allCells) {
      const cellHash = c.id.replace("status-cell-", "").trim().toLowerCase();
      if (cellHash && (cleanHash.startsWith(cellHash) || cellHash.startsWith(cleanHash))) {
        cell = c;
        break;
      }
    }
  }
  if (!cell) return;

  const temAmbos = commit.tem_ambos_ajustes || (commit.has_xml_changes && commit.has_sql_changes);
  if (temAmbos) {
    let fluxoHtml = "";
    if (commit.redmine_id_fluxo) {
      fluxoHtml = `<a href="https://redmine.tjce.jus.br/issues/${commit.redmine_id_fluxo}" target="_blank" class="badge bg-warning text-dark fw-bold text-decoration-none d-inline-flex align-items-center gap-1" title="Redmine de Fluxo (.xml)"><i class="bi bi-diagram-3-fill"></i> #${commit.redmine_id_fluxo}</a>`;
    } else if (commit.is_saved_fluxo) {
      fluxoHtml = `<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle d-inline-flex align-items-center gap-1" title="Fluxo salvo no banco de dados"><i class="bi bi-diagram-3"></i> Fluxo Salvo</span>`;
    } else {
      fluxoHtml = `<span class="badge bg-secondary-subtle text-muted border border-secondary-subtle d-inline-flex align-items-center gap-1" title="Fluxo pendente"><i class="bi bi-diagram-3"></i> Fluxo Pendente</span>`;
    }

    let sqlHtml = "";
    if (commit.redmine_id_sql) {
      sqlHtml = `<a href="https://redmine.tjce.jus.br/issues/${commit.redmine_id_sql}" target="_blank" class="badge text-dark fw-bold text-decoration-none d-inline-flex align-items-center gap-1" style="background-color: #22d3ee;" title="Redmine de Scripts SQL (.sql)"><i class="bi bi-database-fill"></i> #${commit.redmine_id_sql}</a>`;
    } else if (commit.is_saved_sql) {
      sqlHtml = `<span class="badge text-info border border-info-subtle d-inline-flex align-items-center gap-1" style="background-color: rgba(34, 211, 238, 0.15);" title="SQL salvo no banco de dados"><i class="bi bi-database"></i> SQL Salvo</span>`;
    } else {
      sqlHtml = `<span class="badge bg-secondary-subtle text-muted border border-secondary-subtle d-inline-flex align-items-center gap-1" title="SQL pendente"><i class="bi bi-database"></i> SQL Pendente</span>`;
    }

    cell.innerHTML = `<div class="d-flex flex-column gap-1 align-items-center">${fluxoHtml}${sqlHtml}</div>`;
  } else if (commit.redmine_id) {
    if (commit.has_sql_changes) {
      cell.innerHTML = `<a href="https://redmine.tjce.jus.br/issues/${commit.redmine_id}" target="_blank" class="badge text-dark fw-bold text-decoration-none d-inline-flex align-items-center gap-1" style="background-color: #22d3ee;" title="Redmine de Scripts SQL (.sql)"><i class="bi bi-database-fill"></i> #${commit.redmine_id}</a>`;
    } else if (commit.has_xml_changes) {
      cell.innerHTML = `<a href="https://redmine.tjce.jus.br/issues/${commit.redmine_id}" target="_blank" class="badge bg-warning text-dark fw-bold text-decoration-none d-inline-flex align-items-center gap-1" title="Redmine de Fluxo (.xml)"><i class="bi bi-diagram-3-fill"></i> #${commit.redmine_id}</a>`;
    } else {
      cell.innerHTML = `<a href="https://redmine.tjce.jus.br/issues/${commit.redmine_id}" target="_blank" class="badge bg-success text-decoration-none d-inline-flex align-items-center gap-1" title="Abrir tarefa no Redmine"><i class="bi bi-check-circle-fill"></i> #${commit.redmine_id}</a>`;
    }
  } else if (commit.is_saved) {
    if (commit.has_sql_changes) {
      cell.innerHTML = `<span class="badge text-info border border-info-subtle d-inline-flex align-items-center gap-1" style="background-color: rgba(34, 211, 238, 0.15);" title="Item salvo no PostgreSQL"><i class="bi bi-database me-1"></i>Salvo</span>`;
    } else if (commit.has_xml_changes) {
      cell.innerHTML = `<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle d-inline-flex align-items-center gap-1" title="Item salvo no PostgreSQL"><i class="bi bi-diagram-3 me-1"></i>Salvo</span>`;
    } else {
      cell.innerHTML = `<span class="badge bg-success-subtle text-success border border-success-subtle" title="Item de Catálogo já salvo no PostgreSQL"><i class="bi bi-check-circle-fill me-1"></i>Salvo</span>`;
    }
  } else {
    cell.innerHTML = `<span class="badge bg-secondary-subtle text-muted border border-secondary-subtle" title="Não salvo no banco de dados">Não Salvo</span>`;
  }
}

function updateCommitStatusCell(hash, isSaved) {
  if (!hash) return;
  const commit = window.COMMITS_STORE ? window.COMMITS_STORE[hash] : null;
  if (commit) {
    commit.is_saved = isSaved;
    updateTableStatusCell(commit);
  } else {
    updateTableStatusCell({ hash: hash, is_saved: isSaved });
  }
}

/**
 * Handle input changes in IC title, description, or redmine ID
 */
function onICInputChanged() {
  const redmineIdEl = document.getElementById("icInputRedmineId");
  const redmineLinkEl = document.getElementById("icLinkRedmine");
  if (redmineIdEl && redmineLinkEl) {
    const rId = redmineIdEl.value.trim().replace(/^#/, "");
    if (rId) {
      redmineLinkEl.href = `https://redmine.tjce.jus.br/issues/${rId}`;
      redmineLinkEl.classList.remove("d-none");
    } else {
      redmineLinkEl.classList.add("d-none");
    }
  }
}



/**
 * Create IC directly in Redmine via official REST API with live step-by-step logs
 */
async function createICDirectlyInRedmine(btn, isDryRun = false) {
  const titleEl = document.getElementById("icInputTitle");
  const descEl = document.getElementById("icInputDesc");
  const alertEl = document.getElementById("icFeedbackAlert");
  const alertText = document.getElementById("icFeedbackText");
  const logsCont = document.getElementById("icRedmineLogsContainer");
  const logsList = document.getElementById("icRedmineLogsList");
  const logsStatus = document.getElementById("icRedmineLogsStatus");

  const title = titleEl ? titleEl.value.trim() : "";
  const description = descEl ? descEl.value.trim() : "";

  if (!title) {
    if (alertEl && alertText) {
      alertEl.classList.remove("d-none", "alert-success");
      alertEl.classList.add("alert-danger");
      alertText.textContent = "Por favor, informe o título do Item de Catálogo.";
    }
    return;
  }

  if (logsCont) logsCont.classList.remove("d-none");
  if (logsList) logsList.innerHTML = "";
  if (logsStatus) {
    logsStatus.className = "badge bg-warning text-dark";
    logsStatus.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span> Executando';
  }

  const appendLog = (msg, isError = false) => {
    if (!logsList) return;
    const div = document.createElement("div");
    div.className = isError ? "text-danger" : "text-light";
    div.innerHTML = `<span class="${isError ? 'text-danger' : 'text-success'} me-1">${isError ? '✖' : '✔'}</span> ${escapeHtml(msg)}`;
    logsList.appendChild(div);
    if (logsCont) logsCont.scrollTop = logsCont.scrollHeight;
  };

  appendLog(`Iniciando processo de ${isDryRun ? 'SIMULAÇÃO (DRY-RUN)' : 'CRIAÇÃO'} via API do Redmine...`);

  const originalBtnHtml = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = isDryRun 
      ? '<span class="spinner-border spinner-border-sm me-1" role="status"></span> Validando no Redmine...'
      : '<span class="spinner-border spinner-border-sm me-1" role="status"></span> Criando no Redmine...';
  }

  const commitHash = currentModalCommit ? (currentModalCommit.hash || currentModalCommit.short_hash || "") : "";
  const commitUrl = currentModalCommit ? (currentModalCommit.commit_url || currentModalCommit.web_commit_url || "") : "";
  const complexityEl = document.getElementById("icInputComplexity");
  const complexity = complexityEl ? complexityEl.value : (currentModalCommit && currentModalCommit.complexity ? currentModalCommit.complexity : "Baixa");

  const hasXml = currentModalCommit ? (currentModalCommit.has_xml_changes || currentModalCommit.xml_files_count > 0) : false;
  const hasSql = currentModalCommit ? (currentModalCommit.has_sql_changes || currentModalCommit.sql_files_count > 0) : false;
  const hasBoth = currentModalCommit && (currentModalCommit.tem_ambos_ajustes || (hasXml && hasSql));

  // CASO COMMIT MISTO (XML + SQL): Um único clique cria/simula AMBOS os Redmines automaticamente
  if (hasBoth) {
    try {
      const needFluxo = !currentModalCommit.redmine_id_fluxo;
      const needSql = !currentModalCommit.redmine_id_sql;

      if (!needFluxo && !needSql) {
        appendLog(`Ambas as tarefas já foram criadas: #${currentModalCommit.redmine_id_fluxo} (Fluxo) e #${currentModalCommit.redmine_id_sql} (SQL)`);
        if (btn) {
          btn.disabled = false;
          btn.className = "btn btn-success d-flex align-items-center gap-1";
          btn.innerHTML = `<i class="bi bi-box-arrow-up-right"></i> Redmines #${currentModalCommit.redmine_id_fluxo} e #${currentModalCommit.redmine_id_sql}`;
          btn.onclick = () => window.open(`https://redmine.tjce.jus.br/issues/${currentModalCommit.redmine_id_fluxo}`, '_blank');
        }
        return;
      }

      let fluxoIssueId = currentModalCommit.redmine_id_fluxo || null;
      let sqlIssueId = currentModalCommit.redmine_id_sql || null;

      // 1. Processar Redmine Fluxo (XML)
      if (needFluxo) {
        appendLog("[1/2] Processando Redmine de Catálogo da Funcionalidade (Fluxo XML)...");
        const descFluxo = currentModalCommit._edited_desc_fluxo || (window.currentICNature === 'fluxo' ? description : currentModalCommit.ic_description_fluxo) || description;
        const countFluxo = currentModalCommit.ic_count_xml !== undefined ? currentModalCommit.ic_count_xml : (currentModalCommit.ic_count || 1);

        const resFluxo = await fetch("/api/redmine/create-ic", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: title,
            description: descFluxo,
            commit_hash: commitHash,
            commit_url: commitUrl,
            ic_count: countFluxo,
            natureza: "fluxo",
            activity_type: "Desenvolvimento - Criar/Manter tarefa de automação",
            complexity: complexity,
            dry_run: isDryRun,
          }),
        });
        const dataFluxo = await resFluxo.json();
        if (Array.isArray(dataFluxo.logs)) {
          dataFluxo.logs.forEach(msg => appendLog(`[Fluxo] ${msg}`, msg.includes("FALHA") || msg.includes("Erro")));
        }
        if (!dataFluxo.success) {
          throw new Error(dataFluxo.message || "Falha ao criar Redmine de Fluxo.");
        }
        fluxoIssueId = dataFluxo.issue_id;
        currentModalCommit.redmine_id_fluxo = fluxoIssueId;
        currentModalCommit.is_saved_fluxo = true;
        appendLog(`[Fluxo XML] Tarefa #${fluxoIssueId} processada com sucesso!`);
      } else {
        appendLog(`[Fluxo XML] Já emitido anteriormente: #${fluxoIssueId}`);
      }

      // 2. Processar Redmine SQL (Scripts)
      if (needSql) {
        appendLog("[2/2] Processando Redmine de Banco de Dados (Scripts SQL)...");
        const descSql = currentModalCommit._edited_desc_sql || (window.currentICNature === 'sql' ? description : currentModalCommit.ic_description_sql) || description;
        const countSql = currentModalCommit.ic_count_sql !== undefined ? currentModalCommit.ic_count_sql : (currentModalCommit.has_sql_changes ? 1 : 1);

        const resSql = await fetch("/api/redmine/create-ic", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: title,
            description: descSql,
            commit_hash: commitHash,
            commit_url: commitUrl,
            ic_count: countSql,
            natureza: "sql",
            activity_type: "Desenvolvimento - Criar/Manter scripts para extração de dados do banco de dados",
            complexity: complexity,
            dry_run: isDryRun,
          }),
        });
        const dataSql = await resSql.json();
        if (Array.isArray(dataSql.logs)) {
          dataSql.logs.forEach(msg => appendLog(`[SQL] ${msg}`, msg.includes("FALHA") || msg.includes("Erro")));
        }
        if (!dataSql.success) {
          throw new Error(dataSql.message || "Falha ao criar Redmine de Banco de Dados.");
        }
        sqlIssueId = dataSql.issue_id;
        currentModalCommit.redmine_id_sql = sqlIssueId;
        currentModalCommit.is_saved_sql = true;
        appendLog(`[Scripts SQL] Tarefa #${sqlIssueId} processada com sucesso!`);
      } else {
        appendLog(`[Scripts SQL] Já emitido anteriormente: #${sqlIssueId}`);
      }

      // Atualizar commit e storage
      currentModalCommit.is_saved = true;
      currentModalCommit.redmine_id = fluxoIssueId || sqlIssueId;

      if (window.COMMITS_STORE && currentModalCommit.hash && window.COMMITS_STORE[currentModalCommit.hash]) {
        const stored = window.COMMITS_STORE[currentModalCommit.hash];
        stored.redmine_id_fluxo = fluxoIssueId;
        stored.is_saved_fluxo = true;
        stored.redmine_id_sql = sqlIssueId;
        stored.is_saved_sql = true;
        stored.is_saved = true;
        stored.redmine_id = fluxoIssueId || sqlIssueId;
      }

      updateNatureTabBadges(currentModalCommit);
      renderModalForCurrentNature();
      updateTableStatusCell(currentModalCommit);

      if (logsStatus) {
        logsStatus.className = isDryRun ? "badge bg-info text-dark" : "badge bg-success";
        logsStatus.textContent = isDryRun ? "Simulação Concluída (2 Tarefas)" : "Concluído (2 Tarefas)";
      }

      if (btn) {
        btn.disabled = false;
        btn.className = "btn btn-success d-flex align-items-center gap-1";
        btn.innerHTML = `<i class="bi bi-box-arrow-up-right"></i> Redmines #${fluxoIssueId} e #${sqlIssueId}`;
        btn.onclick = () => window.open(`https://redmine.tjce.jus.br/issues/${fluxoIssueId}`, '_blank');
      }

      if (alertEl && alertText) {
        alertEl.classList.remove("d-none", "alert-danger");
        alertEl.classList.add("alert-success");
        const urlFluxo = `https://redmine.tjce.jus.br/issues/${fluxoIssueId}`;
        const urlSql = `https://redmine.tjce.jus.br/issues/${sqlIssueId}`;
        alertText.innerHTML = isDryRun ? `
          <span><i class="bi bi-check-circle-fill text-success me-1"></i><b>Simulação Dupla Concluída com Sucesso!</b> 2 tarefas simuladas e salvas no banco: <b>#${fluxoIssueId} (Fluxo)</b> e <b>#${sqlIssueId} (SQL)</b>.</span>
        ` : `
          <span><b>Sucesso!</b> Ambas as tarefas criadas no Redmine e salvas no banco de dados!</span>
          <a href="${urlFluxo}" target="_blank" class="btn btn-sm btn-outline-success ms-2 py-0 px-2 text-decoration-none">
            #${fluxoIssueId} Fluxo <i class="bi bi-box-arrow-up-right ms-1"></i>
          </a>
          <a href="${urlSql}" target="_blank" class="btn btn-sm btn-outline-info ms-2 py-0 px-2 text-decoration-none">
            #${sqlIssueId} SQL <i class="bi bi-box-arrow-up-right ms-1"></i>
          </a>
        `;
      }
    } catch (err) {
      console.error("Erro no processo duplo:", err);
      appendLog(`Erro: ${err.message}`, true);
      if (logsStatus) {
        logsStatus.className = "badge bg-danger";
        logsStatus.textContent = "Erro";
      }
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalBtnHtml || '<i class="bi bi-cloud-arrow-up-fill"></i> Tentar Novamente';
      }
      if (alertEl && alertText) {
        alertEl.classList.remove("d-none", "alert-success");
        alertEl.classList.add("alert-danger");
        alertText.textContent = `Erro no processo: ${err.message}`;
      }
    }
    return;
  }

  // CASO COMMIT DE NATUREZA ÚNICA (Apenas XML ou Apenas SQL)
  const isOnlySql = hasSql && !hasXml;
  const natureza = isOnlySql ? "sql" : "fluxo";
  const defaultAct = isOnlySql
    ? "Desenvolvimento - Criar/Manter scripts para extração de dados do banco de dados"
    : "Desenvolvimento - Criar/Manter tarefa de automação";
  const inputActivity = document.getElementById("icInputActivityType");
  const activityType = inputActivity ? inputActivity.value : defaultAct;

  const quantityEl = document.getElementById("icInputQuantity");
  let icCount = quantityEl ? parseInt(quantityEl.value, 10) : (currentModalCommit ? (currentModalCommit.ic_count || 1) : 1);
  if (isNaN(icCount) || icCount < 1) icCount = 1;

  try {
    const res = await fetch("/api/redmine/create-ic", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        title: title,
        description: description,
        commit_hash: commitHash,
        commit_url: commitUrl,
        ic_count: icCount,
        natureza: natureza,
        activity_type: activityType,
        complexity: complexity,
        dry_run: isDryRun,
      }),
    });

    const data = await res.json();

    if (logsList) logsList.innerHTML = "";
    if (Array.isArray(data.logs)) {
      data.logs.forEach((stepMsg) => {
        appendLog(stepMsg, stepMsg.includes("FALHA") || stepMsg.includes("Erro"));
      });
    }

    if (data.success) {
      const issueId = data.issue_id;
      const issueUrl = data.issue_url || `https://redmine.tjce.jus.br/issues/${issueId}`;

      // Set Redmine ID and link for both simulation and real creation
      const redmineIdEl = document.getElementById("icInputRedmineId");
      if (redmineIdEl && issueId) {
        redmineIdEl.value = issueId;
      }
      const redmineLinkEl = document.getElementById("icLinkRedmine");
      if (redmineLinkEl && issueId) {
        redmineLinkEl.href = issueUrl;
        redmineLinkEl.classList.remove("d-none");
      }

      // Update currentModalCommit state per nature
      if (currentModalCommit) {
        if (natureza === 'sql') {
          currentModalCommit.redmine_id_sql = issueId;
          currentModalCommit.is_saved_sql = true;
        } else {
          currentModalCommit.redmine_id_fluxo = issueId;
          currentModalCommit.is_saved_fluxo = true;
        }
        currentModalCommit.is_saved = true;
        currentModalCommit.redmine_id = issueId;

        if (window.COMMITS_STORE && currentModalCommit.hash && window.COMMITS_STORE[currentModalCommit.hash]) {
          const stored = window.COMMITS_STORE[currentModalCommit.hash];
          if (natureza === 'sql') {
            stored.redmine_id_sql = issueId;
            stored.is_saved_sql = true;
          } else {
            stored.redmine_id_fluxo = issueId;
            stored.is_saved_fluxo = true;
          }
          stored.is_saved = true;
          stored.redmine_id = issueId;
        }
      }

      // Update tab badges inside modal, re-render current nature, and update table status
      updateNatureTabBadges(currentModalCommit);
      renderModalForCurrentNature();
      updateTableStatusCell(currentModalCommit);

      if (data.dry_run) {
        if (logsStatus) {
          logsStatus.className = "badge bg-info text-dark";
          logsStatus.textContent = "Simulação Aprovada & Salva";
        }

        if (btn) {
          btn.disabled = false;
          btn.className = "btn btn-outline-success d-flex align-items-center gap-1";
          btn.innerHTML = `<i class="bi bi-check2-circle"></i> Simulado (${natureza.toUpperCase()} #${issueId})`;
        }

        if (alertEl && alertText) {
          alertEl.classList.remove("d-none", "alert-danger");
          alertEl.classList.add("alert-success");
          alertText.innerHTML = `
            <span><i class="bi bi-check-circle-fill text-success me-1"></i><b>Simulação (${natureza.toUpperCase()}) Concluída e Salva no Banco!</b> Tarefa simulada <b>#${issueId}</b> registrada no banco de dados com status <i>criado</i> (nenhuma tarefa real foi criada no Redmine).</span>
          `;
        }
      } else {
        if (logsStatus) {
          logsStatus.className = "badge bg-success";
          logsStatus.textContent = "Concluído";
        }

        if (btn) {
          btn.disabled = false;
          btn.className = "btn btn-success d-flex align-items-center gap-1";
          btn.innerHTML = `<i class="bi bi-box-arrow-up-right"></i> Redmine #${issueId}`;
          btn.onclick = () => window.open(issueUrl, '_blank');
        }

        if (alertEl && alertText) {
          alertEl.classList.remove("d-none", "alert-danger");
          alertEl.classList.add("alert-success");
          alertText.innerHTML = `
            <span><b>Sucesso!</b> Tarefa (${natureza.toUpperCase()}) <b>#${issueId}</b> criada no Redmine e salva no banco de dados!</span>
            <a href="${issueUrl}" target="_blank" class="btn btn-sm btn-outline-success ms-2 py-0 px-2 text-decoration-none">
              Abrir Tarefa <i class="bi bi-box-arrow-up-right ms-1"></i>
            </a>
          `;
        }
      }
    } else {
      if (logsStatus) {
        logsStatus.className = "badge bg-danger";
        logsStatus.textContent = "Erro";
      }
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalBtnHtml || '<i class="bi bi-cloud-arrow-up-fill"></i> Tentar Novamente';
      }
      if (alertEl && alertText) {
        alertEl.classList.remove("d-none", "alert-success");
        alertEl.classList.add("alert-danger");
        alertText.textContent = `Erro no processo: ${data.message}`;
      }
    }
  } catch (err) {
    console.error("Erro na requisição /api/redmine/create-ic:", err);
    appendLog(`Erro de conexão local: ${err.message}`, true);
    if (logsStatus) {
      logsStatus.className = "badge bg-danger";
      logsStatus.textContent = "Erro de Rede";
    }
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalBtnHtml || '<i class="bi bi-cloud-arrow-up-fill"></i> Tentar Novamente';
    }
    if (alertEl && alertText) {
      alertEl.classList.remove("d-none", "alert-success");
      alertEl.classList.add("alert-danger");
      alertText.textContent = `Erro de comunicação com o servidor: ${err.message}`;
    }
  }
}



/**
 * Escape string for safe insertion into HTML
 */
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Lazy loading for commits table
 */
async function loadMoreCommits() {
  const configEl = document.getElementById("commitsPagingConfig");
  const btn = document.getElementById("btnLoadMoreCommits");
  const spinner = document.getElementById("loadMoreSpinner");
  const tbody = document.getElementById("commitsTableBody");
  const notice = document.getElementById("noMoreCommitsNotice");
  const countEl = document.getElementById("commitsLoadedCount");

  if (!configEl || !btn || !tbody) return;

  const nextSkip = parseInt(configEl.dataset.nextSkip || "0", 10);
  const query = configEl.dataset.query || "";
  const author = configEl.dataset.author || "";
  const branch = configEl.dataset.branch || "";
  const startDate = configEl.dataset.startDate || "";
  const endDate = configEl.dataset.endDate || "";
  const onlyXml = configEl.dataset.onlyXml === "true";

  btn.disabled = true;
  if (spinner) spinner.classList.remove("d-none");

  try {
    const params = new URLSearchParams({
      skip: String(nextSkip),
      limit: "20",
    });
    if (query) params.append("q", query);
    if (author) params.append("author", author);
    if (branch) params.append("branch", branch);
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    if (onlyXml) params.append("only_xml", "true");

    const res = await fetch(`/api/commits/git-paged?${params.toString()}`);
    const data = await res.json();

    if (data.success && Array.isArray(data.commits)) {
      data.commits.forEach((c) => {
        // Cache in window.COMMITS_STORE
        window.COMMITS_STORE[c.hash] = c;

        // Create table row
        const tr = document.createElement("tr");
        tr.id = `row-commit-${c.hash}`;

        const shortHash = c.short_hash || (c.hash ? c.hash.substring(0, 7) : "");
        const webUrl = c.commit_url || "";

        let hashHtml = "";
        if (webUrl) {
          hashHtml = `
            <a href="${webUrl}" target="_blank" class="badge-hash text-decoration-none d-inline-flex align-items-center gap-1" title="Abrir commit no GitLab/GitHub">
              ${shortHash} <i class="bi bi-box-arrow-up-right" style="font-size: 0.65rem;"></i>
            </a>
            <button type="button" class="btn btn-link btn-sm p-0 text-info copy-btn" data-copy="${webUrl}" title="Copiar link direto do commit">
              <i class="bi bi-link-45deg fs-6"></i>
            </button>
          `;
        } else {
          hashHtml = `<span class="badge-hash">${shortHash}</span>`;
        }
        hashHtml += `
          <button type="button" class="btn btn-link btn-sm p-0 text-muted copy-btn" data-copy="${c.hash}" title="Copiar hash completo">
            <i class="bi bi-clipboard" style="font-size: 0.75rem;"></i>
          </button>
        `;

        let metricsHtml = "";
        if (c.tem_ambos_ajustes) {
          metricsHtml += `
            <span class="badge bg-warning text-dark fw-bold" title="${c.ic_count_xml || 1} IC(s) de Fluxo (XML)">
              <i class="bi bi-diagram-3-fill me-1"></i>${c.ic_count_xml || 1} Fluxo
            </span>
            <span class="badge text-dark fw-bold" style="background-color: #22d3ee;" title="${c.ic_count_sql || 1} IC(s) de Banco (SQL)">
              <i class="bi bi-database-fill me-1"></i>${c.ic_count_sql || 1} SQL
            </span>
          `;
        } else if (c.has_xml_changes) {
          metricsHtml += `
            <span class="badge bg-warning text-dark fw-bold" title="${c.ic_count_xml || c.xml_files_count || 1} IC(s) de Fluxo (XML)">
              <i class="bi bi-diagram-3-fill me-1"></i>${c.ic_count_xml || c.xml_files_count || 1} Fluxo
            </span>
          `;
        } else if (c.has_sql_changes) {
          metricsHtml += `
            <span class="badge text-dark fw-bold" style="background-color: #22d3ee;" title="${c.ic_count_sql || c.sql_files_count || 1} IC(s) de Banco (SQL)">
              <i class="bi bi-database-fill me-1"></i>${c.ic_count_sql || c.sql_files_count || 1} SQL
            </span>
          `;
        }

        if (c.files_count > 0) {
          metricsHtml += `
            <button type="button" class="btn btn-sm btn-secondary-custom py-1 px-2 small" onclick="viewFilesByHash('${c.hash}')">
              <i class="bi bi-file-code me-1 text-info"></i> ${c.files_count} arq
            </button>
          `;
        } else {
          metricsHtml += `<span class="text-muted small">-</span>`;
        }

        let statusHtml = "";
        if (c.tem_ambos_ajustes) {
          let flx = c.redmine_id_fluxo 
            ? `<a href="https://redmine.tjce.jus.br/issues/${c.redmine_id_fluxo}" target="_blank" class="badge bg-warning text-dark fw-bold text-decoration-none d-inline-flex align-items-center gap-1" title="Redmine de Fluxo (.xml)"><i class="bi bi-diagram-3-fill"></i> #${c.redmine_id_fluxo}</a>`
            : (c.is_saved_fluxo ? `<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle d-inline-flex align-items-center gap-1" title="Fluxo salvo no banco de dados"><i class="bi bi-diagram-3"></i> Fluxo Salvo</span>` : `<span class="badge bg-secondary-subtle text-muted border border-secondary-subtle d-inline-flex align-items-center gap-1" title="Fluxo pendente"><i class="bi bi-diagram-3"></i> Fluxo Pendente</span>`);
          let sql = c.redmine_id_sql
            ? `<a href="https://redmine.tjce.jus.br/issues/${c.redmine_id_sql}" target="_blank" class="badge text-dark fw-bold text-decoration-none d-inline-flex align-items-center gap-1" style="background-color: #22d3ee;" title="Redmine de Scripts SQL (.sql)"><i class="bi bi-database-fill"></i> #${c.redmine_id_sql}</a>`
            : (c.is_saved_sql ? `<span class="badge text-info border border-info-subtle d-inline-flex align-items-center gap-1" style="background-color: rgba(34, 211, 238, 0.15);" title="SQL salvo no banco de dados"><i class="bi bi-database"></i> SQL Salvo</span>` : `<span class="badge bg-secondary-subtle text-muted border border-secondary-subtle d-inline-flex align-items-center gap-1" title="SQL pendente"><i class="bi bi-database"></i> SQL Pendente</span>`);
          statusHtml = `<div class="d-flex flex-column gap-1 align-items-center">${flx}${sql}</div>`;
        } else if (c.redmine_id) {
          if (c.has_sql_changes) {
            statusHtml = `<a href="https://redmine.tjce.jus.br/issues/${c.redmine_id}" target="_blank" class="badge text-dark fw-bold text-decoration-none d-inline-flex align-items-center gap-1" style="background-color: #22d3ee;" title="Redmine de Scripts SQL (.sql)"><i class="bi bi-database-fill"></i> #${c.redmine_id}</a>`;
          } else if (c.has_xml_changes) {
            statusHtml = `<a href="https://redmine.tjce.jus.br/issues/${c.redmine_id}" target="_blank" class="badge bg-warning text-dark fw-bold text-decoration-none d-inline-flex align-items-center gap-1" title="Redmine de Fluxo (.xml)"><i class="bi bi-diagram-3-fill"></i> #${c.redmine_id}</a>`;
          } else {
            statusHtml = `<a href="https://redmine.tjce.jus.br/issues/${c.redmine_id}" target="_blank" class="badge bg-success text-decoration-none d-inline-flex align-items-center gap-1" title="Abrir tarefa no Redmine"><i class="bi bi-check-circle-fill"></i> #${c.redmine_id}</a>`;
          }
        } else if (c.is_saved) {
          if (c.has_sql_changes) {
            statusHtml = `<span class="badge text-info border border-info-subtle d-inline-flex align-items-center gap-1" style="background-color: rgba(34, 211, 238, 0.15);" title="Item salvo no PostgreSQL"><i class="bi bi-database me-1"></i>Salvo</span>`;
          } else if (c.has_xml_changes) {
            statusHtml = `<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle d-inline-flex align-items-center gap-1" title="Item salvo no PostgreSQL"><i class="bi bi-diagram-3 me-1"></i>Salvo</span>`;
          } else {
            statusHtml = `<span class="badge bg-success-subtle text-success border border-success-subtle" title="Item de Catálogo já salvo no PostgreSQL"><i class="bi bi-check-circle-fill me-1"></i>Salvo</span>`;
          }
        } else {
          statusHtml = `<span class="badge bg-secondary-subtle text-muted border border-secondary-subtle" title="Não salvo no banco de dados">Não Salvo</span>`;
        }

        const actionHtml = `
          <button type="button" class="btn btn-sm btn-primary-custom py-1 px-2 small d-inline-flex align-items-center gap-1"
                  onclick="openCreateICByHash('${c.hash}')"
                  title="Gerar Item de Catálogo para este commit">
            <i class="bi bi-card-checklist"></i>
            <span>Criar IC</span>
          </button>
        `;

        tr.innerHTML = `
          <td data-col="hash"><div class="d-flex align-items-center gap-1">${hashHtml}</div></td>
          <td data-col="date" class="text-muted small">${c.commit_date || ""}</td>
          <td data-col="author"><div class="fw-medium text-light small">${escapeHtml(c.author || "")}</div></td>
          <td data-col="repo">
            <span class="badge bg-dark border border-secondary text-info small text-truncate d-inline-block" style="max-width: 120px;" title="Repositório: ${escapeHtml(c.repo_name || "Local")}">
              <i class="bi bi-folder2 me-1"></i>${escapeHtml(c.repo_name || "Local")}
            </span>
          </td>
          <td data-col="branch">
            ${c.branch ? `
              <span class="badge bg-primary-subtle text-primary border border-primary-subtle small text-truncate d-inline-block" style="max-width: 140px; font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;" title="Branch de Origem: ${escapeHtml(c.branch)}">
                <i class="bi bi-diagram-2 me-1"></i>${escapeHtml(c.branch)}
              </span>
            ` : `<span class="text-muted small">-</span>`}
          </td>
          <td data-col="message"><div class="text-light">${escapeHtml(c.message || "")}</div></td>
          <td data-col="files" class="text-center">
            <div class="d-flex align-items-center justify-content-center gap-1 flex-wrap">
              ${metricsHtml}
            </div>
          </td>
          <td data-col="status" class="text-center" id="status-cell-${c.hash}">${statusHtml}</td>
          <td data-col="actions" class="text-center">${actionHtml}</td>
        `;

        tbody.appendChild(tr);
      });

      // Apply active column filters to newly added rows
      if (typeof applyTableColumnVisibility === "function") {
        applyTableColumnVisibility();
      }

      // Update total loaded count
      const totalLoaded = tbody.querySelectorAll("tr:not(#emptyCommitsRow)").length;
      if (countEl) countEl.textContent = totalLoaded;

      // Update paging configuration
      configEl.dataset.nextSkip = String(data.next_skip);
      configEl.dataset.hasMore = data.has_more ? "true" : "false";

      // Re-bind clipboard copy buttons for new rows
      if (typeof setupClipboardCopy === "function") {
        setupClipboardCopy();
      }

      // If no more commits, hide button and show notice
      const loadMoreSec = document.getElementById("loadMoreSection");
      if (!data.has_more) {
        if (loadMoreSec) loadMoreSec.classList.add("d-none");
        if (notice) notice.classList.remove("d-none");
      }
    }
  } catch (err) {
    console.error("Erro ao carregar mais commits:", err);
  } finally {
    btn.disabled = false;
    if (spinner) spinner.classList.add("d-none");
  }
}

/**
 * Safe HTML escaping helper
 */
function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Interactive Branch Autocomplete Component
 * Provides real-time filtering, keyboard navigation, and clear actions
 * across all local and remote branches.
 */
function setupBranchAutocomplete() {
  const wrappers = document.querySelectorAll(".branch-autocomplete-wrapper");
  if (!wrappers.length) return;

  // 1. Try to load initial branch data from embedded JSON
  let branchesData = { active: "", local: [], remote: [], selected: "" };
  const dataScript = document.getElementById("branches-data");
  if (dataScript) {
    try {
      branchesData = JSON.parse(dataScript.textContent);
    } catch (e) {
      console.warn("Erro ao fazer parse de branches-data:", e);
    }
  }

  function buildBranchList(data) {
    const list = [];
    // Special option: All branches
    list.push({
      value: "",
      name: "Todas as Branches (--all)",
      type: "all",
      badge: "Todas",
      badgeClass: "bg-secondary text-light",
      icon: "bi-diagram-3",
    });

    // Active branch (if any)
    if (data.active) {
      list.push({
        value: data.active,
        name: data.active,
        type: "active",
        badge: "⭐ Atual",
        badgeClass: "bg-warning text-dark fw-bold",
        icon: "bi-star-fill text-warning",
      });
    }

    // Local branches
    if (Array.isArray(data.local)) {
      data.local.forEach((b) => {
        if (b && b !== data.active) {
          list.push({
            value: b,
            name: b,
            type: "local",
            badge: "Local",
            badgeClass: "bg-primary-subtle text-primary border border-primary-subtle",
            icon: "bi-hdd-network",
          });
        }
      });
    }

    // Remote branches
    if (Array.isArray(data.remote)) {
      data.remote.forEach((b) => {
        if (b) {
          list.push({
            value: b,
            name: b,
            type: "remote",
            badge: "origin",
            badgeClass: "bg-secondary-subtle text-muted",
            icon: "bi-cloud",
          });
        }
      });
    }

    return list;
  }

  let allBranchItems = buildBranchList(branchesData);

  // If no branch data embedded, fetch from API asynchronously
  if (allBranchItems.length <= 1) {
    fetch("/api/git/branches")
      .then((res) => res.json())
      .then((data) => {
        if (data.success) {
          branchesData.active = data.active;
          branchesData.local = data.local;
          branchesData.remote = data.remote;
          allBranchItems = buildBranchList(branchesData);
          wrappers.forEach((w) => updatePlaceholderAndState(w));
        }
      })
      .catch((err) => console.warn("Falha ao buscar branches da API:", err));
  }

  function updatePlaceholderAndState(wrapper) {
    const textInput = wrapper.querySelector(".branch-autocomplete-input");
    const hiddenInput = wrapper.querySelector("input[name='branch']");
    const clearBtn = wrapper.querySelector(".branch-autocomplete-clear");
    if (!textInput || !hiddenInput) return;

    if (hiddenInput.value) {
      textInput.value = hiddenInput.value;
      if (clearBtn) clearBtn.style.display = "inline-flex";
    } else {
      if (clearBtn) clearBtn.style.display = "none";
    }
  }

  wrappers.forEach((wrapper) => {
    const hiddenInput = wrapper.querySelector("input[name='branch']");
    const textInput = wrapper.querySelector(".branch-autocomplete-input");
    const clearBtn = wrapper.querySelector(".branch-autocomplete-clear");
    const toggleBtn = wrapper.querySelector(".branch-autocomplete-toggle");
    const dropdownMenu = wrapper.querySelector(".branch-autocomplete-dropdown");
    const dropdownList = wrapper.querySelector(".branch-dropdown-list");
    const countEl = wrapper.querySelector(".branch-results-count");
    const tabBtns = wrapper.querySelectorAll(".branch-tab");

    if (!hiddenInput || !textInput || !dropdownMenu || !dropdownList) return;

    let activeIndex = -1;
    let currentTab = "all";

    function updateTabCounts() {
      const allTab = wrapper.querySelector(".branch-tab[data-tab='all']");
      const localTab = wrapper.querySelector(".branch-tab[data-tab='local']");
      const remoteTab = wrapper.querySelector(".branch-tab[data-tab='remote']");
      const localCount = allBranchItems.filter((i) => i.type === "local" || i.type === "active").length;
      const remoteCount = allBranchItems.filter((i) => i.type === "remote").length;
      if (allTab) allTab.textContent = `Todas (${Math.max(0, allBranchItems.length - 1)})`;
      if (localTab) localTab.textContent = `Locais (${localCount})`;
      if (remoteTab) remoteTab.textContent = `Remotas (${remoteCount})`;
    }
    updateTabCounts();

    tabBtns.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        currentTab = btn.dataset.tab || "all";
        tabBtns.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        filterAndRender();
        textInput.focus();
      });
    });

    function renderDropdown(items, query) {
      dropdownList.innerHTML = "";
      activeIndex = -1;

      if (countEl) {
        if (query) {
          countEl.textContent = `${items.length} encontrada(s)`;
        } else {
          countEl.textContent = `${items.length} itens`;
        }
      }

      if (!items.length) {
        const emptyDiv = document.createElement("div");
        emptyDiv.className = "branch-dropdown-empty";
        emptyDiv.innerHTML = `<i class="bi bi-search me-1 text-dim"></i> Nenhuma branch encontrada para "<strong>${escapeHtml(query)}</strong>"`;
        dropdownList.appendChild(emptyDiv);
        dropdownMenu.style.display = "block";
        return;
      }

      // Max items to render in DOM for high performance
      const maxToRender = 60;
      const slice = items.slice(0, maxToRender);

      slice.forEach((item, index) => {
        const itemEl = document.createElement("div");
        itemEl.className = "branch-dropdown-item";
        itemEl.dataset.value = item.value;
        itemEl.dataset.index = index;

        const isSelected = (hiddenInput.value || "") === item.value;
        if (isSelected) {
          itemEl.classList.add("is-selected");
        }

        // Highlight matching text in name
        let nameHtml = escapeHtml(item.name);
        if (query && item.name.toLowerCase().includes(query.toLowerCase())) {
          const qEsc = escapeHtml(query);
          const regex = new RegExp(`(${qEsc.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
          nameHtml = nameHtml.replace(regex, '<mark class="branch-highlight">$1</mark>');
        }

        itemEl.innerHTML = `
          <div class="d-flex align-items-center gap-2 text-truncate" style="max-width: 78%;">
            <i class="bi ${item.icon} text-muted flex-shrink-0" style="font-size: 0.75rem;"></i>
            <span class="branch-name-text text-truncate" title="${escapeHtml(item.name)}">${nameHtml}</span>
          </div>
          <div class="d-flex align-items-center gap-1 flex-shrink-0">
            <span class="badge ${item.badgeClass} branch-badge-pill">${item.badge}</span>
            ${isSelected ? '<i class="bi bi-check2 text-primary ms-1" style="font-size: 0.85rem;"></i>' : ''}
          </div>
        `;

        itemEl.addEventListener("mousedown", (e) => {
          e.preventDefault(); // prevent input blur
          selectItem(item.value, item.value ? item.name : "");
        });

        itemEl.addEventListener("mouseenter", () => {
          setActiveIndex(index);
        });

        dropdownList.appendChild(itemEl);
      });

      if (items.length > maxToRender) {
        const moreDiv = document.createElement("div");
        moreDiv.className = "p-2 text-center text-dim small border-top border-secondary border-opacity-25";
        moreDiv.style.fontSize = "0.72rem";
        moreDiv.textContent = `Mostrando 60 de ${items.length} branches. Continue digitando para filtrar...`;
        dropdownList.appendChild(moreDiv);
      }

      dropdownMenu.style.display = "block";
    }

    function setActiveIndex(index) {
      const domItems = dropdownList.querySelectorAll(".branch-dropdown-item");
      domItems.forEach((el) => el.classList.remove("active"));
      if (index >= 0 && index < domItems.length) {
        activeIndex = index;
        const current = domItems[index];
        current.classList.add("active");
        current.scrollIntoView({ block: "nearest" });
      } else {
        activeIndex = -1;
      }
    }

    function filterAndRender() {
      const q = textInput.value.trim().toLowerCase();

      // 1. Filter by current tab
      let tabPool = allBranchItems;
      if (currentTab === "local") {
        tabPool = allBranchItems.filter((i) => i.type === "all" || i.type === "active" || i.type === "local");
      } else if (currentTab === "remote") {
        tabPool = allBranchItems.filter((i) => i.type === "all" || i.type === "remote");
      }

      if (!q) {
        renderDropdown(tabPool, "");
        return;
      }

      // 2. Filter by search query
      const matched = tabPool.filter((item) => {
        if (item.type === "all") {
          return q === "todas" || q === "all" || q === "--all";
        }
        return item.name.toLowerCase().includes(q);
      });

      // Sort with smart ranking:
      // 1. Starts with query
      // 2. Local before remote
      matched.sort((a, b) => {
        if (a.type === "all") return -1;
        if (b.type === "all") return 1;
        const aStarts = a.name.toLowerCase().startsWith(q);
        const bStarts = b.name.toLowerCase().startsWith(q);
        if (aStarts && !bStarts) return -1;
        if (!aStarts && bStarts) return 1;
        if (a.type === "active") return -1;
        if (b.type === "active") return 1;
        if (a.type === "local" && b.type === "remote") return -1;
        if (a.type === "remote" && b.type === "local") return 1;
        return a.name.localeCompare(b.name);
      });

      renderDropdown(matched, q);
    }

    function selectItem(value, displayName) {
      hiddenInput.value = value;
      textInput.value = value || "";
      if (clearBtn) {
        clearBtn.style.display = value ? "inline-flex" : "none";
      }
      closeDropdown();
      textInput.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function closeDropdown() {
      dropdownMenu.style.display = "none";
      activeIndex = -1;
    }

    function openDropdown() {
      filterAndRender();
    }

    // Input events
    textInput.addEventListener("focus", () => {
      openDropdown();
    });

    textInput.addEventListener("input", () => {
      hiddenInput.value = textInput.value.trim();
      if (clearBtn) {
        clearBtn.style.display = textInput.value ? "inline-flex" : "none";
      }
      filterAndRender();
    });

    textInput.addEventListener("keydown", (e) => {
      const isOpen = dropdownMenu.style.display === "block";
      const domItems = dropdownList.querySelectorAll(".branch-dropdown-item");

      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (!isOpen) {
          openDropdown();
        } else {
          let next = activeIndex + 1;
          if (next >= domItems.length) next = 0;
          setActiveIndex(next);
        }
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (isOpen) {
          let prev = activeIndex - 1;
          if (prev < 0) prev = domItems.length - 1;
          setActiveIndex(prev);
        }
      } else if (e.key === "Enter") {
        if (isOpen && activeIndex >= 0 && domItems[activeIndex]) {
          e.preventDefault();
          const selectedVal = domItems[activeIndex].dataset.value;
          selectItem(selectedVal, selectedVal);
        } else if (isOpen) {
          if (domItems.length === 1) {
            e.preventDefault();
            const val = domItems[0].dataset.value;
            selectItem(val, val);
          } else {
            closeDropdown();
          }
        }
      } else if (e.key === "Escape") {
        if (isOpen) {
          e.preventDefault();
          closeDropdown();
        }
      } else if (e.key === "Tab") {
        closeDropdown();
      }
    });

    // Clear button
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        selectItem("", "");
        textInput.focus();
        openDropdown();
      });
    }

    // Toggle button
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        if (dropdownMenu.style.display === "block") {
          closeDropdown();
        } else {
          textInput.focus();
          openDropdown();
        }
      });
    }

    // Click outside to close
    document.addEventListener("click", (e) => {
      if (!wrapper.contains(e.target)) {
        closeDropdown();
      }
    });

    // Initial state
    updatePlaceholderAndState(wrapper);
  });
}
