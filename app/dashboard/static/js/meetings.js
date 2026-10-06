/**
 * Productivity Assistant - Meetings & Teams Calls Dashboard Controller
 */

let activeMeetingIds = [];

// Format helper
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function toggleSelectAllMeetings(master) {
  const checkboxes = document.querySelectorAll(".meeting-checkbox");
  checkboxes.forEach((cb) => (cb.checked = master.checked));
  updateSelectedMeetingsBar();
}

function updateSelectedMeetingsBar() {
  const checkboxes = document.querySelectorAll(".meeting-checkbox:checked");
  const bar = document.getElementById("selectedMeetingsBar");
  const badge = document.getElementById("selectedCountBadge");

  if (!bar || !badge) return;

  if (checkboxes.length > 0) {
    bar.classList.remove("d-none");
    badge.textContent = checkboxes.length;
  } else {
    bar.classList.add("d-none");
  }
}

function clearSelectedMeetings() {
  const checkboxes = document.querySelectorAll(".meeting-checkbox");
  checkboxes.forEach((cb) => (cb.checked = false));
  const master = document.getElementById("selectAllMeetings");
  if (master) master.checked = false;
  updateSelectedMeetingsBar();
}

function openMeetingICModal(id, title, contact, duration, dateStr) {
  activeMeetingIds = [id];

  const modalEl = document.getElementById("meetingICModal");
  if (!modalEl) return;

  const countBadge = document.getElementById("meetingCountBadge");
  const titleInput = document.getElementById("meetingInputTitle");
  const quantityInput = document.getElementById("meetingInputQuantity");
  const descInput = document.getElementById("meetingInputDesc");
  const feedbackAlert = document.getElementById("meetingFeedbackAlert");
  const logsContainer = document.getElementById("meetingRedmineLogsContainer");

  if (countBadge) countBadge.textContent = "1 Chamada / Reunião";
  if (quantityInput) quantityInput.value = 1;
  if (feedbackAlert) feedbackAlert.classList.add("d-none");
  if (logsContainer) logsContainer.classList.add("d-none");

  const cleanTitle = contact ? `Alinhamento com ${contact}` : title;
  if (titleInput) titleInput.value = cleanTitle;

  if (descInput) {
    descInput.value = [
      `Atividade: ${cleanTitle}`,
      `Contato / Participante: ${contact || "Equipe PJe"}`,
      `Data e Horário: ${dateStr}`,
      `Duração: ${duration}`,
      `Tipo: Chamada avulsa 1:1 via Microsoft Teams`,
      ``,
      `Objetivo: Alinhamento técnico de desenvolvimento, regras de negócio e suporte PJe.`,
      `Evidência: Chamada registrada via Productivity Assistant.`,
    ].join("\n");
  }

  const modal = new bootstrap.Modal(modalEl);
  modal.show();
}

function openConsolidatedMeetingICModal() {
  const checkboxes = Array.from(document.querySelectorAll(".meeting-checkbox:checked"));
  if (checkboxes.length === 0) return;

  activeMeetingIds = checkboxes.map((cb) => parseInt(cb.value, 10));

  const modalEl = document.getElementById("meetingICModal");
  if (!modalEl) return;

  const countBadge = document.getElementById("meetingCountBadge");
  const titleInput = document.getElementById("meetingInputTitle");
  const quantityInput = document.getElementById("meetingInputQuantity");
  const descInput = document.getElementById("meetingInputDesc");
  const feedbackAlert = document.getElementById("meetingFeedbackAlert");
  const logsContainer = document.getElementById("meetingRedmineLogsContainer");

  if (countBadge) countBadge.textContent = `${activeMeetingIds.length} Chamadas Selecionadas`;
  if (quantityInput) quantityInput.value = activeMeetingIds.length;
  if (feedbackAlert) feedbackAlert.classList.add("d-none");
  if (logsContainer) logsContainer.classList.add("d-none");

  const now = new Date();
  const monthName = now.toLocaleString("pt-BR", { month: "long" });
  const defaultTitle = `Alinhamentos técnicos e suporte à equipe - ${monthName}/${now.getFullYear()}`;
  if (titleInput) titleInput.value = defaultTitle;

  // Gather details from selected rows
  const lines = [
    `Atividade: ${defaultTitle}`,
    `Total de Reuniões / Chamadas: ${activeMeetingIds.length}`,
    ``,
    `Detalhamento das Chamadas Realizadas (Evidência Microsoft Teams):`,
    `| Data e Horário | Contato / Participante | Duração |`,
    `|---|---|---|`,
  ];

  activeMeetingIds.forEach((id) => {
    const row = document.getElementById(`meeting-row-${id}`);
    if (row) {
      const contactEl = row.querySelector(".fw-semibold");
      const timeEl = row.querySelector(".font-monospace");
      const durEl = row.querySelector(".badge.bg-dark");
      const contact = contactEl ? contactEl.textContent.trim() : `Chamada #${id}`;
      const time = timeEl ? timeEl.textContent.trim() : "";
      const dur = durEl ? durEl.textContent.trim() : "";
      lines.push(`| ${time} | ${contact} | ${dur} |`);
    }
  });

  lines.push(``);
  lines.push(`Nota: Levantamento e auditoria gerados automaticamente via Productivity Assistant.`);

  if (descInput) descInput.value = lines.join("\n");

  const modal = new bootstrap.Modal(modalEl);
  modal.show();
}

async function executeMeetingICCreation(btn, isDryRun = false) {
  const titleInput = document.getElementById("meetingInputTitle");
  const activityInput = document.getElementById("meetingInputActivity");
  const complexityInput = document.getElementById("meetingInputComplexity");
  const quantityInput = document.getElementById("meetingInputQuantity");
  const descInput = document.getElementById("meetingInputDesc");
  const feedbackAlert = document.getElementById("meetingFeedbackAlert");
  const feedbackText = document.getElementById("meetingFeedbackText");
  const logsContainer = document.getElementById("meetingRedmineLogsContainer");
  const logsList = document.getElementById("meetingRedmineLogsList");
  const logsStatus = document.getElementById("meetingRedmineLogsStatus");

  const title = titleInput ? titleInput.value.trim() : "";
  const activityType = activityInput ? activityInput.value : "";
  const complexity = complexityInput ? complexityInput.value : "Baixa";
  const description = descInput ? descInput.value.trim() : "";

  if (!title) {
    alert("Por favor, informe o título do Item de Catálogo.");
    return;
  }

  if (logsContainer) logsContainer.classList.remove("d-none");
  if (logsList) logsList.innerHTML = "";
  if (logsStatus) {
    logsStatus.className = "badge bg-warning text-dark";
    logsStatus.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Executando';
  }

  const appendLog = (msg, isError = false) => {
    if (!logsList) return;
    const div = document.createElement("div");
    div.className = isError ? "text-danger" : "text-light";
    div.innerHTML = `<span class="${isError ? "text-danger" : "text-success"} me-1">${isError ? "✖" : "✔"}</span> ${escapeHtml(msg)}`;
    logsList.appendChild(div);
    if (logsContainer) logsContainer.scrollTop = logsContainer.scrollHeight;
  };

  appendLog(`Iniciando processo de ${isDryRun ? "SIMULAÇÃO (DRY-RUN)" : "CRIAÇÃO"} de IC no Redmine...`);

  const originalHtml = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = isDryRun 
      ? '<span class="spinner-border spinner-border-sm me-1"></span> Validando no Redmine...'
      : '<span class="spinner-border spinner-border-sm me-1"></span> Criando no Redmine...';
  }

  try {
    const res = await fetch("/api/meetings/create-ic", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        meeting_ids: activeMeetingIds,
        title: title,
        description: description,
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
      if (data.dry_run) {
        if (logsStatus) {
          logsStatus.className = "badge bg-info text-dark";
          logsStatus.textContent = "Simulação Aprovada & Salva";
        }
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<i class="bi bi-shield-check"></i> Testar Novamente (Simulação)';
        }
        if (feedbackAlert && feedbackText) {
          feedbackAlert.classList.remove("d-none", "alert-danger");
          feedbackAlert.classList.add("alert-success");
          feedbackText.innerHTML = `
            <span><i class="bi bi-check-circle-fill text-success me-1"></i><b>Simulação Concluída e Salva no Banco!</b> Tarefa simulada <b>#${data.issue_id}</b> registrada no banco de dados com status <i>salvo</i>.</span>
          `;
        }

        // Update rows in table
        activeMeetingIds.forEach((id) => {
          const statusCell = document.getElementById(`meeting-status-${id}`);
          if (statusCell) {
            statusCell.innerHTML = `
              <span class="badge bg-success-subtle text-success border border-success-subtle" title="Item de Catálogo já salvo no PostgreSQL (#${data.issue_id})">
                <i class="bi bi-check-circle-fill me-1"></i>Salvo
              </span>
            `;
          }
        });
      } else {
        if (logsStatus) {
          logsStatus.className = "badge bg-success";
          logsStatus.textContent = "Concluído";
        }
        if (btn) {
          btn.disabled = false;
          btn.className = "btn btn-success d-flex align-items-center gap-1";
          btn.innerHTML = `<i class="bi bi-box-arrow-up-right"></i> Redmine #${data.issue_id}`;
          btn.onclick = () => window.open(data.issue_url || `https://redmine.tjce.jus.br/issues/${data.issue_id}`, "_blank");
        }
        if (feedbackAlert && feedbackText) {
          feedbackAlert.classList.remove("d-none", "alert-danger");
          feedbackAlert.classList.add("alert-success");
          feedbackText.innerHTML = `
            <span><b>Sucesso!</b> Tarefa <b>#${data.issue_id}</b> criada no Redmine e salva no banco de dados!</span>
            <a href="${data.issue_url || `https://redmine.tjce.jus.br/issues/${data.issue_id}`}" target="_blank" class="btn btn-sm btn-outline-success ms-2 py-0 px-2 text-decoration-none">
              Abrir Tarefa <i class="bi bi-box-arrow-up-right ms-1"></i>
            </a>
          `;
        }

        // Update rows in table
        activeMeetingIds.forEach((id) => {
          const statusCell = document.getElementById(`meeting-status-${id}`);
          if (statusCell) {
            statusCell.innerHTML = `
              <a href="${data.issue_url || `https://redmine.tjce.jus.br/issues/${data.issue_id}`}" target="_blank" class="badge bg-success text-decoration-none d-inline-flex align-items-center gap-1" title="Abrir tarefa no Redmine">
                <i class="bi bi-check-circle-fill"></i> #${data.issue_id}
              </a>
            `;
          }
        });
      }
    } else {
      if (logsStatus) {
        logsStatus.className = "badge bg-danger";
        logsStatus.textContent = "Erro";
      }
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalHtml || '<i class="bi bi-cloud-arrow-up-fill"></i> Tentar Novamente';
      }
      if (feedbackAlert && feedbackText) {
        feedbackAlert.classList.remove("d-none", "alert-success");
        feedbackAlert.classList.add("alert-danger");
        feedbackText.textContent = `Erro: ${data.message}`;
      }
    }
  } catch (err) {
    appendLog(`Erro de conexão local: ${err.message}`, true);
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalHtml || '<i class="bi bi-cloud-arrow-up-fill"></i> Tentar Novamente';
    }
  }
}

function openManualMeetingModal() {
  const modalEl = document.getElementById("manualCallModal");
  if (!modalEl) return;
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  const dtInput = document.getElementById("manualDateTime");
  if (dtInput) dtInput.value = now.toISOString().slice(0, 16);

  const modal = new bootstrap.Modal(modalEl);
  modal.show();
}

async function submitManualCall() {
  const contact = document.getElementById("manualContactName").value.trim();
  const callType = document.getElementById("manualCallType").value;
  const duration = document.getElementById("manualDuration").value.trim();
  const dateStr = document.getElementById("manualDateTime").value;
  const title = document.getElementById("manualTitle").value.trim();

  if (!contact) {
    alert("Por favor, informe o nome do contato.");
    return;
  }

  try {
    const res = await fetch("/api/meetings/create-manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contact_name: contact,
        call_type: callType,
        duration: duration || "30m",
        date_str: dateStr,
        title: title || `Alinhamento com ${contact}`,
      }),
    });
    const data = await res.json();
    if (data.success) {
      window.location.reload();
    } else {
      alert("Erro ao salvar: " + data.message);
    }
  } catch (err) {
    alert("Falha de comunicação: " + err.message);
  }
}

async function deleteSelectedMeetings() {
  const checkboxes = Array.from(document.querySelectorAll(".meeting-checkbox:checked"));
  const ids = checkboxes.map((cb) => parseInt(cb.value, 10));

  const confirmMsg = ids.length > 0 
    ? `Deseja realmente excluir as ${ids.length} chamadas selecionadas?`
    : "Deseja excluir TODAS as chamadas do sistema?";

  if (!confirm(confirmMsg)) return;

  try {
    const res = await fetch("/api/meetings/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ meeting_ids: ids }),
    });
    const data = await res.json();
    if (data.success) {
      window.location.reload();
    }
  } catch (err) {
    alert("Erro ao excluir: " + err.message);
  }
}

function showBookmarkletInstructions() {
  const modalEl = document.getElementById("bookmarkletInstructionsModal");
  if (modalEl) {
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
  }
}

async function copyBookmarkletCode(btn) {
  try {
    const res = await fetch("/static/js/teams_bookmarklet.js?t=" + Date.now());
    const code = await res.text();
    await navigator.clipboard.writeText(code);
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-check2 text-success me-1"></i> Código Copiado!';
    setTimeout(() => (btn.innerHTML = orig), 2500);
    alert(
      "✅ Código do Extrator copiado com sucesso!\n\n" +
      "Agora faça o seguinte:\n" +
      "1. Abra a aba do Teams Web (onde está seu Histórico de Chamadas);\n" +
      "2. Pressione F12 no teclado para abrir o Console do Desenvolvedor;\n" +
      "3. Cole com Ctrl + V e aperte Enter.\n\n" +
      "O painel do Productivity Assistant aparecerá instantaneamente no Teams!"
    );
  } catch (err) {
    alert("Erro ao copiar código: " + err.message);
  }
}

function openPasteJsonModal() {
  const modalEl = document.getElementById("pasteJsonModal");
  if (!modalEl) return;
  const textarea = document.getElementById("pastedJsonTextarea");
  if (textarea) textarea.value = "";
  const modal = new bootstrap.Modal(modalEl);
  modal.show();
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    const textarea = document.getElementById("pastedJsonTextarea");
    if (textarea && text) {
      textarea.value = text;
    }
  } catch (err) {
    alert("Não foi possível acessar a área de transferência automaticamente. Por favor, clique na caixa de texto e pressione Ctrl + V.");
  }
}

async function submitPastedJson() {
  const textarea = document.getElementById("pastedJsonTextarea");
  const raw = textarea ? textarea.value.trim() : "";
  if (!raw) {
    alert("Por favor, cole o JSON com as chamadas.");
    return;
  }
  let calls = [];
  try {
    const parsed = JSON.parse(raw);
    calls = Array.isArray(parsed) ? parsed : (parsed.calls || [parsed]);
  } catch (err) {
    alert("JSON inválido: " + err.message);
    return;
  }

  if (calls.length === 0) {
    alert("Nenhuma chamada encontrada no JSON informado.");
    return;
  }

  try {
    const res = await fetch("/api/meetings/import-teams-calls", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ calls }),
    });
    const data = await res.json();
    if (data.success) {
      window.location.reload();
    } else {
      alert("Erro ao importar: " + data.message);
    }
  } catch (err) {
    alert("Falha de conexão: " + err.message);
  }
}

/**
 * Copy full IC format (Title + Description) directly for Redmine
 */
async function copyFullMeetingICToRedmine(btn) {
  const titleEl = document.getElementById("meetingInputTitle");
  const descEl = document.getElementById("meetingInputDesc");
  const alertEl = document.getElementById("meetingFeedbackAlert");
  const alertText = document.getElementById("meetingFeedbackText");

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
    console.error("Erro ao copiar IC de reunião:", err);
  }
}

