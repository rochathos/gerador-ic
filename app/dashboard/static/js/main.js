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
    let listHtml = '<ul class="list-group list-group-flush bg-transparent">';
    files.forEach(f => {
      listHtml += `
        <li class="list-group-item bg-transparent text-light border-secondary d-flex align-items-center gap-2 py-2">
          <i class="bi bi-file-earmark-code text-info"></i>
          <span class="font-monospace small">${f}</span>
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
