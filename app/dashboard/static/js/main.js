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
