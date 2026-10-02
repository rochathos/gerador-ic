/**
 * Productivity Assistant - Teams Web Call History Extractor
 * Compatible with Chrome Trusted Types (no innerHTML, no script.src)
 * Specialized for Microsoft Teams Web accessibility aria-labels
 */
(function () {
  const SERVER_URL = "http://localhost:8000/api/meetings/import-teams-calls";

  // Remove existing widget if already injected
  const oldWidget = document.getElementById("pa-teams-extractor-widget");
  if (oldWidget) oldWidget.remove();

  // Helper to create element with styles and text
  function el(tag, style, text) {
    const element = document.createElement(tag);
    if (style) element.style.cssText = style;
    if (text !== undefined && text !== null) element.textContent = text;
    return element;
  }

  // Create UI overlay container
  const widget = el("div", `
    position: fixed;
    bottom: 24px;
    right: 24px;
    width: 420px;
    max-height: 520px;
    background: #0f172a;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 12px;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.7), 0 10px 10px -5px rgba(0, 0, 0, 0.4);
    z-index: 9999999;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 13px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  `);
  widget.id = "pa-teams-extractor-widget";

  // Header
  const header = el("div", "background: #1e293b; padding: 12px 16px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center;");
  const titleBox = el("div", "display: flex; align-items: center; gap: 8px; font-weight: 600; color: #38bdf8;");
  const iconSpan = el("span", "", "📞");
  const titleText = el("span", "", "Productivity Assistant");
  titleBox.appendChild(iconSpan);
  titleBox.appendChild(titleText);

  const closeBtn = el("button", "background: transparent; border: none; color: #94a3b8; font-size: 20px; cursor: pointer; line-height: 1; padding: 0 6px;", "×");
  closeBtn.onclick = () => widget.remove();
  header.appendChild(titleBox);
  header.appendChild(closeBtn);
  widget.appendChild(header);

  // Body
  const body = el("div", "padding: 16px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 12px;");
  const statusBox = el("div", "font-size: 13px; color: #cbd5e1; line-height: 1.4;");
  const listBox = el("div", "display: flex; flex-direction: column; gap: 8px; max-height: 240px; overflow-y: auto;");
  body.appendChild(statusBox);
  body.appendChild(listBox);
  widget.appendChild(body);

  // Footer
  const footer = el("div", "background: #1e293b; padding: 12px 16px; border-top: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; gap: 8px;");
  const summarySpan = el("span", "color: #94a3b8; font-size: 12px;", "0 chamadas");
  
  const actionsBox = el("div", "display: flex; gap: 8px; align-items: center;");
  const copyBtn = el("button", "background: #475569; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 12px; display: none;", "📋 Copiar JSON");
  const sendBtn = el("button", "background: #2563eb; color: #fff; border: none; padding: 6px 14px; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 12px;", "Enviar para o Sistema");

  actionsBox.appendChild(copyBtn);
  actionsBox.appendChild(sendBtn);
  footer.appendChild(summarySpan);
  footer.appendChild(actionsBox);
  widget.appendChild(footer);

  document.body.appendChild(widget);

  // Parse a call from an aria-label or DOM row
  function parseCallItem(el) {
    let label = el.getAttribute("aria-label") || "";
    if (!label || !label.includes("Dura")) {
      const sub = el.querySelector('[aria-label*="Dura"], [aria-label*="chamada"], [aria-label*="Chamada"]');
      if (sub) label = sub.getAttribute("aria-label") || "";
    }

    const innerText = el.innerText || "";

    // Strategy 1: Accurate Portuguese aria-label parsing
    // Example: "Helio Matheus Sales Silva, Entrada, Duração da chamada de 1 minuto  44 segundos, A data/hora da chamada é Ontem"
    if (label && (label.includes("Dura") || label.includes("data/hora") || label.includes("Entrada") || label.includes("Saída"))) {
      if (/perdid|missed/i.test(label) || /perdid|missed/i.test(innerText)) return null;

      // 1. Call Type
      let callType = "efetuada";
      if (/entrada|recebid|incoming/i.test(label)) {
        callType = "recebida";
      }

      // 2. Contact Name
      let contactName = "";
      const nameMatch = label.match(/^([^,]+?)(?:,\s*(?:entrada|sa[íi]da|recebida|efetuada)|\s*,)/i);
      if (nameMatch) {
        contactName = nameMatch[1].trim();
      } else {
        contactName = label.split(",")[0].trim();
      }
      if (!contactName || contactName.length < 2) {
        contactName = "Colega Teams";
      }

      // 3. Duration: "Duração da chamada de 1 minuto  44 segundos"
      let duration = "15m";
      const durMatch = label.match(/Dura[çc][ãa]o(?: da chamada)?(?: de)?\s*([^,]+)/i);
      if (durMatch) {
        const rawDur = durMatch[1].trim();
        let h = 0, m = 0, s = 0;
        const hm = rawDur.match(/(\d+)\s*(?:hora|horas|h)/i);
        const mm = rawDur.match(/(\d+)\s*(?:minuto|minutos|min|m)/i);
        const sm = rawDur.match(/(\d+)\s*(?:segundo|segundos|seg|s)/i);
        if (hm) h = parseInt(hm[1], 10);
        if (mm) m = parseInt(mm[1], 10);
        if (sm) s = parseInt(sm[1], 10);
        const parts = [];
        if (h > 0) parts.push(`${h}h`);
        if (m > 0) parts.push(`${m}m`);
        if (s > 0 && h === 0) parts.push(`${s}s`);
        duration = parts.length > 0 ? parts.join(" ") : rawDur;
      }

      // 4. Date: "A data/hora da chamada é Ontem"
      let dateStr = "Hoje";
      const dateMatch = label.match(/data\/hora(?: da chamada)?(?: é)?\s*([^,]+)/i);
      if (dateMatch) {
        dateStr = dateMatch[1].trim();
      }

      // If innerText contains time of day (e.g. 14:35), attach it
      const timeMatch = innerText.match(/\b([01]?\d|2[0-3]):[0-5]\d\b/);
      if (timeMatch && !dateStr.includes(":")) {
        dateStr += ` às ${timeMatch[0]}`;
      }

      return {
        contact_name: contactName,
        title: `Alinhamento com ${contactName}`,
        call_type: callType,
        duration: duration,
        date_str: dateStr
      };
    }

    // Strategy 2: Fallback text parsing if no aria-label
    if (innerText && innerText.length > 5) {
      if (/perdid|missed/i.test(innerText)) return null;

      let callType = /recebid|incoming/i.test(innerText) ? "recebida" : "efetuada";
      const lines = innerText.split("\n").map(l => l.trim()).filter(Boolean);
      let contactName = lines[0] || "Colega Teams";
      if (contactName.includes(":") || /^\d/.test(contactName) || /chamada/i.test(contactName)) {
        contactName = lines[1] || contactName;
      }

      let duration = "15m";
      const durMatch = innerText.match(/(\d+)\s*h(?:\s*(\d+)\s*m)?|(\d+)\s*m(?:in)?(?:\s*(\d+)\s*s)?|(\d{1,2}:\d{2}(?::\d{2})?)/i);
      if (durMatch && durMatch[0]) {
        duration = durMatch[0].trim();
      }

      let dateStr = "Hoje";
      for (const line of lines) {
        if (/hoje|ontem|\d{1,2}\/\d{1,2}|\d{1,2}\s+de\s+[a-zç]+/i.test(line)) {
          dateStr = line;
          break;
        }
      }

      return {
        contact_name: contactName,
        title: `Alinhamento com ${contactName}`,
        call_type: callType,
        duration: duration,
        date_str: dateStr
      };
    }

    return null;
  }

  // Extraction logic
  function extractCalls() {
    const calls = [];
    const seen = new Set();

    // Query candidate rows and aria-label elements
    const elements = document.querySelectorAll(
      '[aria-label*="Dura\u00e7\u00e3o"], [aria-label*="chamada"], [aria-label*="Chamada"], [data-tid="calls-history-list"] [role="row"], [data-tid="calls-history-list"] [role="listitem"], [data-tid*="call-history-item"], [data-tid*="call"], [class*="call-history"], [class*="callRow"], [role="row"], [role="listitem"]'
    );

    elements.forEach((el) => {
      const parsed = parseCallItem(el);
      if (parsed && parsed.contact_name) {
        const key = `${parsed.contact_name}_${parsed.date_str}_${parsed.duration}`;
        if (!seen.has(key)) {
          seen.add(key);
          calls.push(parsed);
        }
      }
    });

    return calls;
  }

  function render() {
    while (listBox.firstChild) {
      listBox.removeChild(listBox.firstChild);
    }
    const calls = extractCalls();

    if (calls.length > 0) {
      statusBox.textContent = `✅ Encontradas ${calls.length} chamadas no histórico do Teams:`;
      statusBox.style.color = "#38bdf8";
      summarySpan.textContent = `${calls.length} chamadas`;
      copyBtn.style.display = "inline-block";

      calls.forEach((c) => {
        const row = el("div", "background: #1e293b; padding: 8px 10px; border-radius: 6px; font-size: 12px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #334155;");
        const left = el("div");
        const nameEl = el("div", "font-weight: 600; color: #f8fafc;", c.contact_name);
        const metaEl = el("div", "font-size: 11px; color: #94a3b8;", `${c.date_str} • ${c.call_type}`);
        left.appendChild(nameEl);
        left.appendChild(metaEl);

        const durBadge = el("span", "background: #0369a1; color: #e0f2fe; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600;", c.duration);
        row.appendChild(left);
        row.appendChild(durBadge);
        listBox.appendChild(row);
      });

      // Copy JSON button
      copyBtn.onclick = async () => {
        try {
          await navigator.clipboard.writeText(JSON.stringify(calls, null, 2));
          copyBtn.textContent = "✅ JSON Copiado!";
          statusBox.textContent = "📋 Dados copiados para a área de transferência! No painel, clique em 'Colar Chamadas (JSON)'.";
          statusBox.style.color = "#34d399";
        } catch (e) {
          prompt("Copie os dados das chamadas (JSON) abaixo:", JSON.stringify(calls));
        }
      };

      // Send to server
      sendBtn.textContent = "Enviar para o Sistema";
      sendBtn.onclick = async () => {
        sendBtn.disabled = true;
        sendBtn.textContent = "Enviando...";
        try {
          const resp = await fetch(SERVER_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ calls: calls }),
          });
          const data = await resp.json();
          if (data.success) {
            statusBox.textContent = `🎉 ${data.count || calls.length} chamadas importadas com sucesso!`;
            statusBox.style.color = "#34d399";
            sendBtn.style.background = "#10b981";
            sendBtn.textContent = "Concluído!";
            setTimeout(() => {
              if (confirm("Chamadas importadas com sucesso! Deseja abrir a tela de Reuniões agora?")) {
                window.open("http://localhost:8000/meetings", "_blank");
              }
            }, 600);
          } else {
            statusBox.textContent = `⚠️ Erro retornado pelo sistema: ${data.message}`;
            statusBox.style.color = "#f87171";
            sendBtn.disabled = false;
            sendBtn.textContent = "Tentar Novamente";
          }
        } catch (err) {
          statusBox.textContent = "⚠️ O Teams bloqueou a conexão direta de rede (CSP). Clique em 'Copiar JSON' ao lado e cole no painel!";
          statusBox.style.color = "#fbbf24";
          copyBtn.style.background = "#2563eb";
          copyBtn.style.color = "#fff";
        }
      };
    } else {
      statusBox.textContent = "⚠️ Nenhuma chamada detectada na tela atual. No menu lateral do Teams, clique em Chamadas > Histórico e clique em 'Atualizar' abaixo.";
      statusBox.style.color = "#fbbf24";
      summarySpan.textContent = "0 chamadas";
      sendBtn.textContent = "Atualizar Busca";
      sendBtn.onclick = () => render();
    }
  }

  render();
})();
