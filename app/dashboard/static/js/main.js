/**
 * Productivity Assistant - JavaScript Utilities
 */

document.addEventListener("DOMContentLoaded", () => {
  setupQuickFilters();
  setupClipboardCopy();
  setupSearchForm();
});

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
  if (form && overlay) {
    form.addEventListener("submit", () => {
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
    try {
      commit = JSON.parse(commitData);
    } catch (e) {
      console.error("Erro ao converter dados do commit:", e);
      return;
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
    saveBtn.disabled = false;
    saveBtn.innerHTML = '<i class="bi bi-database-add"></i> Salvar no Banco';
    saveBtn.className = "btn btn-outline-success d-flex align-items-center gap-1";
  }

  // Populate badge
  const shortHash = commit.short_hash || (commit.hash ? commit.hash.substring(0, 7) : "");
  if (badgeEl) {
    badgeEl.textContent = `Commit ${shortHash}`;
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

    if (commit.files_changed && commit.files_changed.length > 0) {
      lines.push("");
      lines.push("Arquivos Alterados:");
      let xmlCount = 0;
      commit.files_changed.forEach(f => {
        const isObj = typeof f === "object";
        const path = isObj ? (f.path || f.filename) : String(f);
        const isXml = isObj ? f.is_xml : path.toLowerCase().endsWith(".xml");
        const ins = isObj ? (f.insertions || 0) : 0;
        const del = isObj ? (f.deletions || 0) : 0;
        const diff = (ins || del) ? ` (+${ins} / -${del})` : "";
        if (isXml) {
          xmlCount++;
          lines.push(`- [XML] ${path}${diff}`);
        } else {
          lines.push(`- ${path}${diff}`);
        }
      });
      if (xmlCount > 0) {
        lines.push(`(Total de arquivos XML alterados: ${xmlCount})`);
      }
    }
    icDesc = lines.join("\n");
  }

  if (descEl) {
    descEl.value = icDesc;
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
