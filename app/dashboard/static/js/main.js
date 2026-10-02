/**
 * Productivity Assistant - JavaScript Utilities
 */

document.addEventListener("DOMContentLoaded", () => {
  initCommitsStore();
  setupQuickFilters();
  setupClipboardCopy();
  setupSearchForm();
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
 * Open Create Catalog Item (IC) Modal by commit hash
 */
async function openCreateICByHash(commitHash) {
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

  if (!commit) {
    try {
      const res = await fetch(`/api/commits/inspect/${encodeURIComponent(commitHash)}`);
      const data = await res.json();
      if (data.success && data.commit) {
        commit = data.commit;
        window.COMMITS_STORE[commit.hash] = commit;
      }
    } catch (err) {
      console.error("Erro ao inspecionar commit:", err);
    }
  }

  if (commit) {
    openCreateICModal(commit);
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

  if (!commit) {
    try {
      const res = await fetch(`/api/commits/inspect/${encodeURIComponent(commitHash)}`);
      const data = await res.json();
      if (data.success && data.commit) {
        commit = data.commit;
        window.COMMITS_STORE[commit.hash] = commit;
      }
    } catch (err) {
      console.error("Erro ao inspecionar commit para arquivos:", err);
    }
  }

  if (commit && commit.files_changed) {
    viewFiles(commitHash, commit.files_changed);
  } else {
    viewFiles(commitHash, []);
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
  const saveToDbCheck = document.getElementById("save_to_db");
  const subtitle = document.getElementById("loading-overlay-subtitle");

  if (form && overlay) {
    form.addEventListener("submit", () => {
      if (subtitle) {
        if (saveToDbCheck && saveToDbCheck.checked) {
          subtitle.textContent = "Buscando dados no Git e persistindo no PostgreSQL...";
        } else {
          subtitle.textContent = "Consultando commits no Git em tempo real...";
        }
      }
      overlay.classList.add("active");
    });
  }
}

/**
 * Open files changed modal
 */
function viewFiles(commitHash, filesJson) {
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

  if (!files || files.length === 0) {
    modalBody.innerHTML = '<p class="text-muted">Nenhum arquivo listado ou alterado.</p>';
  } else {
    // Check if any XML files exist and sum their stats
    let xmlCount = 0;
    let totalXmlIns = 0;
    let totalXmlDel = 0;
    let totalXmlLines = 0;

    files.forEach(f => {
      const isXml = typeof f === "object" ? f.is_xml : String(f).toLowerCase().endsWith(".xml");
      if (isXml) {
        xmlCount++;
        if (typeof f === "object") {
          totalXmlIns += (f.insertions || 0);
          totalXmlDel += (f.deletions || 0);
          totalXmlLines += (f.lines || 0);
        }
      }
    });

    let headerHtml = "";
    if (xmlCount > 0) {
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
            <div class="d-flex gap-2">
              <span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1">+${totalXmlIns} adições</span>
              <span class="badge bg-danger-subtle text-danger border border-danger-subtle px-2 py-1">-${totalXmlDel} remoções</span>
              <span class="badge bg-warning text-dark fw-bold px-2 py-1">${totalXmlLines} edições totais</span>
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

      listHtml += `
        <li class="list-group-item bg-dark bg-opacity-50 rounded-2 border ${isXml ? 'border-warning border-opacity-50' : 'border-secondary border-opacity-25'} p-2 d-flex flex-wrap align-items-center justify-content-between gap-2">
          <div class="d-flex align-items-center gap-2 text-truncate" style="max-width: 65%;">
            ${isXml ? '<span class="badge bg-warning text-dark fw-bold" style="font-size:0.7rem;"><i class="bi bi-filetype-xml"></i> XML</span>' : '<i class="bi bi-file-earmark-code text-info"></i>'}
            <span class="font-monospace small ${isXml ? 'text-warning fw-semibold' : 'text-light'} text-truncate" title="${filePath}">${filePath}</span>
          </div>
          <div class="d-flex align-items-center gap-1 font-monospace" style="font-size: 0.8rem;">
            ${isObj && (ins > 0 || del > 0 || lines > 0) ? `
              <span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1" title="Linhas inseridas">+${ins}</span>
              <span class="badge bg-danger-subtle text-danger border border-danger-subtle px-2 py-1" title="Linhas deletadas">-${del}</span>
              <span class="badge bg-secondary-subtle text-light border border-secondary px-2 py-1" title="Total de edições">${lines} edições</span>
            ` : '<span class="text-muted small">Modificado</span>'}
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
function openCreateICModal(commitData) {
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
  const descEl = document.getElementById("icInputDesc");
  const alertEl = document.getElementById("icFeedbackAlert");
  const alertText = document.getElementById("icFeedbackText");
  const saveBtn = document.getElementById("btnSaveICToDB");

  // Reset feedback alert and save button
  if (alertEl) {
    alertEl.classList.add("d-none");
    alertEl.classList.remove("alert-danger");
    alertEl.classList.add("alert-success");
  }
  if (alertText) {
    alertText.textContent = "";
  }
  if (saveBtn) {
    if (commit.is_saved) {
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<i class="bi bi-check-circle-fill"></i> Salvo no Banco';
      saveBtn.className = "btn btn-success d-flex align-items-center gap-1";
    } else {
      saveBtn.disabled = false;
      saveBtn.innerHTML = '<i class="bi bi-database-add"></i> Salvar no Banco';
      saveBtn.className = "btn btn-outline-success d-flex align-items-center gap-1";
    }
  }

  // Reset Redmine button & logs
  const redmineBtn = document.getElementById("btnCreateICInRedmine");
  if (redmineBtn) {
    if (commit.redmine_id) {
      redmineBtn.className = "btn btn-success d-flex align-items-center gap-1";
      redmineBtn.innerHTML = `<i class="bi bi-box-arrow-up-right"></i> Redmine #${commit.redmine_id}`;
      redmineBtn.disabled = false;
      redmineBtn.onclick = () => window.open(`https://redmine.tjce.jus.br/issues/${commit.redmine_id}`, '_blank');
    } else {
      redmineBtn.className = "btn btn-warning text-dark fw-bold d-flex align-items-center gap-1";
      redmineBtn.innerHTML = '<i class="bi bi-cloud-arrow-up-fill"></i> Criar no Redmine';
      redmineBtn.disabled = false;
      redmineBtn.onclick = function() { createICDirectlyInRedmine(this); };
    }
  }

  const redmineLogsCont = document.getElementById("icRedmineLogsContainer");
  const redmineLogsList = document.getElementById("icRedmineLogsList");
  const redmineLogsStatus = document.getElementById("icRedmineLogsStatus");
  if (redmineLogsCont) redmineLogsCont.classList.add("d-none");
  if (redmineLogsList) redmineLogsList.innerHTML = "";
  if (redmineLogsStatus) {
    redmineLogsStatus.className = "badge bg-secondary";
    redmineLogsStatus.textContent = "Aguardando";
  }

  // Populate badge
  const shortHash = commit.short_hash || (commit.hash ? commit.hash.substring(0, 7) : "");
  if (badgeEl) {
    badgeEl.textContent = `Commit ${shortHash}`;
  }

  // Populate IC tags breakdown alert (icf.sh rule)
  const tagsAlert = document.getElementById("icTagsAlert");
  const countText = document.getElementById("icCountText");
  const tagsDetail = document.getElementById("icTagsDetail");

  const rawMetrics = commit.xml_tags_metrics || {};
  let addedTags = {};
  let removedTags = {};
  let totalAdded = 0;
  let totalRemoved = 0;
  const flows = rawMetrics.flows || null;

  if (rawMetrics.added !== undefined || rawMetrics.removed !== undefined) {
    addedTags = rawMetrics.added || {};
    removedTags = rawMetrics.removed || {};
    totalAdded = rawMetrics.total_added !== undefined ? rawMetrics.total_added : Object.values(addedTags).reduce((a, b) => a + b, 0);
    totalRemoved = rawMetrics.total_removed !== undefined ? rawMetrics.total_removed : Object.values(removedTags).reduce((a, b) => a + b, 0);
  } else if (typeof rawMetrics === "object") {
    addedTags = rawMetrics;
    totalAdded = Object.values(addedTags).reduce((a, b) => a + b, 0);
  }

  const effectiveTotalICs = commit.ic_count || (totalAdded + totalRemoved);

  if (tagsAlert && countText && tagsDetail) {
    if (effectiveTotalICs > 0) {
      tagsAlert.classList.remove("d-none");
      let countLabel = `${effectiveTotalICs} Item(ns) de Catálogo (IC) calculados`;
      if (totalAdded > 0 && totalRemoved > 0) {
        countLabel += ` (${totalAdded} adicionadas, ${totalRemoved} removidas)`;
      } else if (totalAdded > 0) {
        countLabel += ` (+${totalAdded} adições)`;
      } else if (totalRemoved > 0) {
        countLabel += ` (-${totalRemoved} remoções)`;
      }
      countText.textContent = countLabel;

      let htmlBadges = "";
      if (flows && Object.keys(flows).length > 0) {
        Object.entries(flows).forEach(([flowPath, flowData]) => {
          const fAdded = flowData.added || {};
          const fRemoved = flowData.removed || {};
          const fTotalAdded = flowData.total_added || Object.values(fAdded).reduce((a, b) => a + b, 0);
          const fTotalRemoved = flowData.total_removed || Object.values(fRemoved).reduce((a, b) => a + b, 0);
          const fTotal = flowData.total_ics || (fTotalAdded + fTotalRemoved);
          if (fTotal === 0) return;

          htmlBadges += `<div class="p-2 mb-2 rounded bg-dark bg-opacity-50 border border-secondary border-opacity-25 w-100">`;
          htmlBadges += `<div class="fw-semibold text-warning small mb-1 d-flex align-items-center justify-content-between"><span><i class="bi bi-file-earmark-code me-1"></i>Fluxo: <span class="text-light">${flowPath}</span></span><span class="badge bg-warning text-dark fw-bold">${fTotal} ICs</span></div>`;

          const fAddEntries = Object.entries(fAdded).sort((a, b) => b[1] - a[1]);
          const fRemEntries = Object.entries(fRemoved).sort((a, b) => b[1] - a[1]);

          if (fAddEntries.length > 0) {
            htmlBadges += `<div class="d-flex align-items-center gap-1 flex-wrap mb-1"><span class="text-success small fw-bold me-1"><i class="bi bi-plus-circle me-1"></i>Adicionadas (+${fTotalAdded}):</span>`;
            htmlBadges += fAddEntries.map(([t, c]) => `<span class="badge bg-success bg-opacity-25 text-success border border-success-subtle fw-semibold px-2 py-1">&lt;${t}&gt;: ${c}</span>`).join(" ");
            htmlBadges += `</div>`;
          }

          if (fRemEntries.length > 0) {
            htmlBadges += `<div class="d-flex align-items-center gap-1 flex-wrap"><span class="text-danger small fw-bold me-1"><i class="bi bi-dash-circle me-1"></i>Removidas (-${fTotalRemoved}):</span>`;
            htmlBadges += fRemEntries.map(([t, c]) => `<span class="badge bg-danger bg-opacity-25 text-danger border border-danger-subtle fw-semibold px-2 py-1">&lt;${t}&gt;: ${c}</span>`).join(" ");
            htmlBadges += `</div>`;
          }
          htmlBadges += `</div>`;
        });
      } else {
        const addEntries = Object.entries(addedTags).sort((a, b) => b[1] - a[1]);
        const remEntries = Object.entries(removedTags).sort((a, b) => b[1] - a[1]);

        if (addEntries.length > 0) {
          htmlBadges += `<div class="d-flex align-items-center gap-1 flex-wrap mb-1"><span class="text-success small fw-bold me-1"><i class="bi bi-plus-circle me-1"></i>Adicionadas (+${totalAdded}):</span>`;
          htmlBadges += addEntries.map(([t, c]) => `<span class="badge bg-success bg-opacity-25 text-success border border-success-subtle fw-semibold px-2 py-1">&lt;${t}&gt;: ${c}</span>`).join(" ");
          htmlBadges += `</div>`;
        }

        if (remEntries.length > 0) {
          htmlBadges += `<div class="d-flex align-items-center gap-1 flex-wrap"><span class="text-danger small fw-bold me-1"><i class="bi bi-dash-circle me-1"></i>Removidas (-${totalRemoved}):</span>`;
          htmlBadges += remEntries.map(([t, c]) => `<span class="badge bg-danger bg-opacity-25 text-danger border border-danger-subtle fw-semibold px-2 py-1">&lt;${t}&gt;: ${c}</span>`).join(" ");
          htmlBadges += `</div>`;
        }
      }

      tagsDetail.innerHTML = htmlBadges || `<span class="text-muted small">Tags válidas calculadas.</span>`;
    } else {
      tagsAlert.classList.add("d-none");
      countText.textContent = "";
      tagsDetail.innerHTML = "";
    }
  }

  // Populate title
  let icTitle = commit.ic_title;
  if (!icTitle && commit.message) {
    icTitle = commit.message.split("\n")[0].trim().substring(0, 180);
  }
  if (titleEl) {
    titleEl.value = icTitle || "Atividade de Desenvolvimento";
  }

  // Populate description
  let icDesc = commit.ic_description;
  if (!icDesc) {
    const dateStr = commit.commit_date || "";
    const author = commit.author || "";
    const url = commit.commit_url || "";
    const lines = [
      `Commit: ${shortHash}`,
      `Data: ${dateStr}`,
      `Autor: ${author}`
    ];
    if (url) lines.push(`Link: ${url}`);
    lines.push("");
    lines.push("Descrição:");
    lines.push((commit.message || "").trim());

    if (effectiveTotalICs > 0) {
      lines.push("");
      let countSummary = "";
      if (totalAdded > 0 && totalRemoved > 0) {
        countSummary = ` (${totalAdded} adicionadas, ${totalRemoved} removidas)`;
      } else if (totalAdded > 0) {
        countSummary = ` (+${totalAdded} adições)`;
      } else if (totalRemoved > 0) {
        countSummary = ` (-${totalRemoved} remoções)`;
      }
      lines.push(`Itens de Catálogo (IC) calculados: ${effectiveTotalICs} IC(s)${countSummary}`);
    }

    if (commit.files_changed && commit.files_changed.length > 0) {
      lines.push("");
      lines.push("Arquivos Alterados:");
      let xmlCount = 0;
      const matchedFlows = new Set();

      commit.files_changed.forEach(f => {
        const isObj = typeof f === "object";
        const rawPath = isObj ? (f.path || f.filename) : String(f);
        const path = decodeGitPath(rawPath);
        const isXml = isObj ? f.is_xml : path.toLowerCase().endsWith(".xml");
        const ins = isObj ? (f.insertions || 0) : 0;
        const del = isObj ? (f.deletions || 0) : 0;
        const diff = (ins || del) ? ` (+${ins} / -${del})` : "";

        if (isXml) {
          xmlCount++;
          lines.push(`- [XML] ${path}${diff}`);

          const flowData = findFlowMetricsForFile(path, flows);
          if (flowData) {
            matchedFlows.add(flowData.path || path);
            const fAdded = flowData.added || {};
            const fRemoved = flowData.removed || {};
            const fTotalAdded = flowData.total_added || Object.values(fAdded).reduce((a, b) => a + b, 0);
            const fTotalRemoved = flowData.total_removed || Object.values(fRemoved).reduce((a, b) => a + b, 0);

            if (Object.keys(fAdded).length > 0) {
              lines.push(`  * Tags Adicionadas (+${fTotalAdded}):`);
              Object.entries(fAdded).sort((a, b) => b[1] - a[1]).forEach(([t, c]) => {
                lines.push(`    * <${t}>: ${c}`);
              });
            }
            if (Object.keys(fRemoved).length > 0) {
              lines.push(`  * Tags Removidas (-${fTotalRemoved}):`);
              Object.entries(fRemoved).sort((a, b) => b[1] - a[1]).forEach(([t, c]) => {
                lines.push(`    * <${t}>: ${c}`);
              });
            }
          }
        } else {
          lines.push(`- ${path}${diff}`);
        }
      });

      // Fallback for flows not in files_changed
      if (flows) {
        Object.entries(flows).forEach(([fPath, fData]) => {
          if ((fData.total_ics || 0) > 0 && !matchedFlows.has(fPath)) {
            const flowCheck = findFlowMetricsForFile(fPath, Object.fromEntries([...matchedFlows].map(p => [p, {}])));
            if (!flowCheck) {
              xmlCount++;
              lines.push(`- [XML] ${fPath}`);
              const fAdded = fData.added || {};
              const fRemoved = fData.removed || {};
              const fTotalAdded = fData.total_added || Object.values(fAdded).reduce((a, b) => a + b, 0);
              const fTotalRemoved = fData.total_removed || Object.values(fRemoved).reduce((a, b) => a + b, 0);
              if (Object.keys(fAdded).length > 0) {
                lines.push(`  * Tags Adicionadas (+${fTotalAdded}):`);
                Object.entries(fAdded).sort((a, b) => b[1] - a[1]).forEach(([t, c]) => {
                  lines.push(`    * <${t}>: ${c}`);
                });
              }
              if (Object.keys(fRemoved).length > 0) {
                lines.push(`  * Tags Removidas (-${fTotalRemoved}):`);
                Object.entries(fRemoved).sort((a, b) => b[1] - a[1]).forEach(([t, c]) => {
                  lines.push(`    * <${t}>: ${c}`);
                });
              }
            }
          }
        });
      }

      if (xmlCount > 0) {
        lines.push(`(Total de arquivos XML alterados: ${xmlCount})`);
      }
    } else if (flows && Object.keys(flows).length > 0) {
      lines.push("");
      lines.push("Arquivos Alterados:");
      let xmlCount = 0;
      Object.entries(flows).forEach(([fPath, fData]) => {
        if ((fData.total_ics || 0) > 0) {
          xmlCount++;
          lines.push(`- [XML] ${fPath}`);
          const fAdded = fData.added || {};
          const fRemoved = fData.removed || {};
          const fTotalAdded = fData.total_added || Object.values(fAdded).reduce((a, b) => a + b, 0);
          const fTotalRemoved = fData.total_removed || Object.values(fRemoved).reduce((a, b) => a + b, 0);
          if (Object.keys(fAdded).length > 0) {
            lines.push(`  * Tags Adicionadas (+${fTotalAdded}):`);
            Object.entries(fAdded).sort((a, b) => b[1] - a[1]).forEach(([t, c]) => {
              lines.push(`    * <${t}>: ${c}`);
            });
          }
          if (Object.keys(fRemoved).length > 0) {
            lines.push(`  * Tags Removidas (-${fTotalRemoved}):`);
            Object.entries(fRemoved).sort((a, b) => b[1] - a[1]).forEach(([t, c]) => {
              lines.push(`    * <${t}>: ${c}`);
            });
          }
        }
      });
      if (xmlCount > 0) {
        lines.push(`(Total de arquivos XML alterados: ${xmlCount})`);
      }
    } else if (effectiveTotalICs > 0 && (Object.keys(addedTags).length > 0 || Object.keys(removedTags).length > 0)) {
      lines.push("");
      lines.push("Tags XML Alteradas:");
      if (Object.keys(addedTags).length > 0) {
        lines.push(`- Tags Adicionadas (+${totalAdded}):`);
        Object.entries(addedTags).sort((a, b) => b[1] - a[1]).forEach(([t, c]) => {
          lines.push(`  * <${t}>: ${c}`);
        });
      }
      if (Object.keys(removedTags).length > 0) {
        lines.push(`- Tags Removidas (-${totalRemoved}):`);
        Object.entries(removedTags).sort((a, b) => b[1] - a[1]).forEach(([t, c]) => {
          lines.push(`  * <${t}>: ${c}`);
        });
      }
    }
    icDesc = lines.join("\n");
  }

  if (descEl) {
    descEl.value = icDesc;
  }

  // Populate Complexity and Quantity fields
  const complexityEl = document.getElementById("icInputComplexity");
  if (complexityEl) {
    complexityEl.value = commit.complexity || "Baixa";
  }
  const quantityEl = document.getElementById("icInputQuantity");
  if (quantityEl) {
    quantityEl.value = effectiveTotalICs > 0 ? effectiveTotalICs : 1;
  }

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

  const fullText = `TÍTULO:\n${title}\n\nDESCRIÇÃO:\n${desc}`;

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
      alertText.textContent = "Título e descrição copiados com sucesso! Cole diretamente no Redmine.";
    }
  } catch (err) {
    console.error("Erro ao copiar IC completo:", err);
  }
}

/**
 * Save the created IC into PostgreSQL database via /api/create-ic
 */
async function saveICToDatabase(btn) {
  const titleEl = document.getElementById("icInputTitle");
  const descEl = document.getElementById("icInputDesc");
  const alertEl = document.getElementById("icFeedbackAlert");
  const alertText = document.getElementById("icFeedbackText");

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

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span> Salvando...';
  }

  try {
    const res = await fetch("/api/create-ic", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        title: title,
        description: description,
        status: "sugerido",
        commit_hash: currentModalCommit ? (currentModalCommit.hash || currentModalCommit.short_hash) : "",
      }),
    });

    const data = await res.json();
    if (data.success) {
      if (btn) {
        btn.className = "btn btn-success d-flex align-items-center gap-1";
        btn.innerHTML = '<i class="bi bi-check-circle-fill"></i> Salvo no Banco';
      }
      if (alertEl && alertText) {
        alertEl.classList.remove("d-none", "alert-danger");
        alertEl.classList.add("alert-success");
        alertText.textContent = `Item de Catálogo #${data.id} salvo com sucesso no banco de dados!`;
      }
      if (currentModalCommit && currentModalCommit.hash) {
        currentModalCommit.is_saved = true;
        const cell = document.getElementById(`status-cell-${currentModalCommit.hash}`);
        if (cell) {
          cell.innerHTML = `
            <span class="badge bg-success-subtle text-success border border-success-subtle" title="Item de Catálogo já salvo no PostgreSQL">
              <i class="bi bi-check-circle-fill me-1"></i>Salvo
            </span>
          `;
        }
      }
    } else {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-database-add"></i> Tentar Novamente';
      }
      if (alertEl && alertText) {
        alertEl.classList.remove("d-none", "alert-success");
        alertEl.classList.add("alert-danger");
        alertText.textContent = `Erro ao salvar: ${data.message}`;
      }
    }
  } catch (err) {
    console.error("Erro na requisição /api/create-ic:", err);
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-database-add"></i> Tentar Novamente';
    }
    if (alertEl && alertText) {
      alertEl.classList.remove("d-none", "alert-success");
      alertEl.classList.add("alert-danger");
      alertText.textContent = `Erro de comunicação com o servidor: ${err.message}`;
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

  // Read complexity and quantity directly from modal inputs
  const complexityEl = document.getElementById("icInputComplexity");
  const quantityEl = document.getElementById("icInputQuantity");
  const complexity = complexityEl ? complexityEl.value : (currentModalCommit && currentModalCommit.complexity ? currentModalCommit.complexity : "Baixa");
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
        activity_type: "Desenvolvimento - Criar/Manter tarefa de automação",
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
      if (data.dry_run) {
        if (logsStatus) {
          logsStatus.className = "badge bg-info text-dark";
          logsStatus.textContent = "Simulação Aprovada";
        }

        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<i class="bi bi-shield-check"></i> Testar Novamente (Simulação)';
        }

        if (alertEl && alertText) {
          alertEl.classList.remove("d-none", "alert-danger");
          alertEl.classList.add("alert-success");
          alertText.innerHTML = `
            <span><i class="bi bi-check-circle-fill text-success me-1"></i><b>Simulação Concluída com 100% de Sucesso!</b> Todas as etapas da API (usuário, projeto, tracker e campos customizados) foram aprovadas. <u>Nenhuma tarefa foi criada</u> no Redmine.</span>
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
          btn.innerHTML = `<i class="bi bi-box-arrow-up-right"></i> Redmine #${data.issue_id}`;
          btn.onclick = () => window.open(data.issue_url, '_blank');
        }

        // Also mark Save to DB button as saved
        const dbBtn = document.getElementById("btnSaveICToDB");
        if (dbBtn) {
          dbBtn.className = "btn btn-success d-flex align-items-center gap-1";
          dbBtn.innerHTML = '<i class="bi bi-check-circle-fill"></i> Salvo no Banco';
        }

        if (alertEl && alertText) {
          alertEl.classList.remove("d-none", "alert-danger");
          alertEl.classList.add("alert-success");
          alertText.innerHTML = `
            <span><b>Sucesso!</b> Tarefa <b>#${data.issue_id}</b> criada no Redmine!</span>
            <a href="${data.issue_url}" target="_blank" class="btn btn-sm btn-outline-success ms-2 py-0 px-2 text-decoration-none">
              Abrir Tarefa <i class="bi bi-box-arrow-up-right ms-1"></i>
            </a>
          `;
        }

        // Update currentModalCommit and table row
        if (currentModalCommit) {
          currentModalCommit.is_saved = true;
          currentModalCommit.redmine_id = data.issue_id;

          const cell = document.getElementById(`status-cell-${currentModalCommit.hash}`);
          if (cell) {
            cell.innerHTML = `
              <a href="${data.issue_url}" target="_blank" class="badge bg-success text-decoration-none d-inline-flex align-items-center gap-1" title="Abrir tarefa no Redmine">
                <i class="bi bi-check-circle-fill"></i> #${data.issue_id}
              </a>
            `;
          }
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
        if (c.ic_count && c.ic_count > 0) {
          metricsHtml += `
            <span class="badge bg-warning text-dark fw-bold" title="${c.ic_count} IC(s) calculados (+${c.ic_added_count || 0} add / -${c.ic_removed_count || 0} rem)">
              <i class="bi bi-tag-fill me-1"></i>${c.ic_count} ICs
            </span>
          `;
        } else if (c.has_xml_changes) {
          metricsHtml += `
            <span class="badge bg-warning text-dark" title="${c.xml_files_count || 0} arquivo(s) XML">
              <i class="bi bi-filetype-xml"></i> ${c.xml_files_count || 0} XML
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
        if (c.is_saved) {
          statusHtml = `
            <span class="badge bg-success-subtle text-success border border-success-subtle" title="Item de Catálogo já salvo no PostgreSQL">
              <i class="bi bi-check-circle-fill me-1"></i>Salvo
            </span>
          `;
        } else {
          statusHtml = `
            <span class="badge bg-secondary-subtle text-muted border border-secondary-subtle" title="Não salvo no banco de dados">
              Não Salvo
            </span>
          `;
        }

        tr.innerHTML = `
          <td><div class="d-flex align-items-center gap-1">${hashHtml}</div></td>
          <td class="text-muted small">${c.commit_date || ""}</td>
          <td><div class="fw-medium text-light small">${escapeHtml(c.author || "")}</div></td>
          <td>
            <span class="badge bg-dark border border-secondary text-info small">
              <i class="bi bi-folder2 me-1"></i>${escapeHtml(c.repo_name || "Local")}
            </span>
          </td>
          <td><div class="text-light">${escapeHtml(c.message || "")}</div></td>
          <td class="text-center">
            <div class="d-flex align-items-center justify-content-center gap-1 flex-wrap">
              ${metricsHtml}
            </div>
          </td>
          <td class="text-center" id="status-cell-${c.hash}">${statusHtml}</td>
          <td class="text-center">
            <button type="button" class="btn btn-sm btn-primary-custom py-1 px-2 small d-inline-flex align-items-center gap-1"
                    onclick="openCreateICByHash('${c.hash}')"
                    title="Gerar Item de Catálogo (IC) para este commit">
              <i class="bi bi-card-checklist"></i>
              <span>Criar IC</span>
            </button>
          </td>
        `;

        tbody.appendChild(tr);
      });

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
