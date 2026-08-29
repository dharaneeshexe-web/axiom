/* GrokCheckout — client */
(function () {
  "use strict";

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  const chatLog = $("#chatLog");
  const traceLog = $("#traceLog");
  const chatInput = $("#chatInput");
  const sendBtn = $("#sendBtn");
  const micBtn = $("#micBtn");
  const voiceBtn = $("#voiceBtn");
  const stagePill = $("#stagePill");
  const skuCard = $("#skuCard");
  const payBox = $("#payBox");
  const laminarLink = $("#laminarLink");
  const catBtn = $("#catBtn");
  const catalog = $("#catalog");
  const catGroups = $("#catGroups");
  const catLoading = $("#catLoading");

  let sessionId = null;
  let busy = false;
  let autoConfirmTimer = null;
  let lastTraceId = null;

  /* ---- Voice (browser-only, ₹0, no server) ---- */
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = SpeechRecognition ? new SpeechRecognition() : null;
  let listening = false;
  let voiceOn = false;
  let speakQueue = [];
  let speaking = false;

  if (recognition) {
    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (ev) => {
      const text = ev.results[0][0].transcript.trim();
      stopMic();
      setMicState(false);
      if (text) send(text);
    };
    recognition.onend = () => {
      setMicState(false);
      listening = false;
    };
    recognition.onerror = (ev) => {
      setMicState(false);
      listening = false;
      if (ev.error === "not-allowed") {
        addAgentMsg("Microphone permission was denied. Type your request instead.");
      } else if (ev.error === "no-speech") {
        addAgentMsg("I didn't catch that. Try speaking again.");
      }
    };
  }

  function speak(text) {
    if (!voiceOn || !window.speechSynthesis) return;
    const clean = String(text || "")
      .replace(/Razorpay/g, "Razor pay")
      .replace(/UPI/g, "U P I")
      .replace(/iPhone/g, "iPhone");
    speakQueue.push({ text: clean });
    pumpSpeak();
  }

  function pumpSpeak() {
    if (speaking || !speakQueue.length || !window.speechSynthesis) return;
    const item = speakQueue.shift();
    const utter = new SpeechSynthesisUtterance(item.text);
    utter.lang = "en-IN";
    utter.rate = 1.02;
    utter.pitch = 1;
    utter.onend = () => { speaking = false; pumpSpeak(); };
    utter.onerror = () => { speaking = false; pumpSpeak(); };
    speaking = true;
    window.speechSynthesis.speak(utter);
  }

  function toggleVoice() {
    voiceOn = !voiceOn;
    voiceBtn.textContent = voiceOn ? "VOICE ON" : "VOICE OFF";
    voiceBtn.classList.toggle("on", voiceOn);
    if (!voiceOn) {
      speakQueue = [];
      if (window.speechSynthesis) window.speechSynthesis.cancel();
    }
  }

  function setMicState(on) {
    micBtn.classList.toggle("listening", on);
    micBtn.title = on ? "Listening… click to stop" : "Talk to the agent (browser voice)";
  }

  function startMic() {
    if (!recognition) {
      addAgentMsg("Voice input isn't supported in this browser. Use Chrome or Edge.");
      return;
    }
    if (listening) { stopMic(); return; }
    listening = true;
    setMicState(true);
    recognition.start();
  }

  function stopMic() {
    if (recognition) {
      try { recognition.stop(); } catch (e) { /* noop */ }
    }
    listening = false;
    micBtn.classList.remove("listening");
    chatInput.focus();
  }

  if (!recognition) {
    micBtn.disabled = true;
    micBtn.title = "Voice input not supported in this browser";
  }

  const LAMINAR_PROJECT = "ed6e32ed-eb7f-4fd0-aae6-fdc5476dc4b4";
  const STAGE_LABELS = {
    browse: "Browse",
    select: "Select",
    confirm: "Confirm",
    execute: "Execute",
    done: "Done",
  };

  function rupee(paise) {
    return "\u20B9" + (paise / 100).toLocaleString("en-IN");
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function setStage(stage, extra) {
    stagePill.textContent = STAGE_LABELS[stage] || stage;
    stagePill.className = "stage-pill";
    if (stage === "select" || stage === "execute") stagePill.classList.add("live");
    else if (stage === "done") stagePill.classList.add("done");
    else if (stage === "confirm") stagePill.classList.add("warn");
  }

  function addUserMsg(text) {
    const el = document.createElement("div");
    el.className = "msg user";
    el.innerHTML = `<span class="who">you</span><div class="bubble">${esc(text)}</div>`;
    chatLog.appendChild(el);
    scrollChat();
  }

  function addAgentMsg(text) {
    const el = document.createElement("div");
    el.className = "msg agent";
    el.innerHTML = `<span class="who">agent</span><div class="bubble">${esc(text)}</div>`;
    chatLog.appendChild(el);
    scrollChat();
    return el;
  }

  function addVariantOptions(options) {
    const host = document.createElement("div");
    host.className = "msg agent";
    host.innerHTML = `<span class="who">agent</span><div class="variants"></div>`;
    const list = $(".variants", host);
    options.forEach((o) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "variant-btn";
      b.innerHTML =
        `<span><span class="variant-summary">${esc(o.summary || o.label)}</span></span>` +
        `<span class="variant-price">${rupee(o.price_rupees * 100)}</span>`;
      b.addEventListener("click", () => send(o.summary || o.label));
      list.appendChild(b);
    });
    chatLog.appendChild(host);
    scrollChat();
  }

  function addMetaNote(text, isError, orderId) {
    const el = document.createElement("div");
    el.className = "meta-note" + (isError ? " err" : "");
    el.innerHTML =
      `<span class="dot"></span>` +
      (orderId ? `<span class="ord">${esc(orderId)}</span>` : "") +
      `<span>${esc(text)}</span>`;
    chatLog.appendChild(el);
    scrollChat();
  }

  function scrollChat() {
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function clearTraceLog() {
    traceLog.innerHTML = "";
  }

  function renderTrace(spans) {
    clearTraceLog();
    if (!spans || !spans.length) {
      traceLog.innerHTML =
        `<div class="empty-state"><div class="empty-orbit"></div><p>Waiting for a decision.</p></div>`;
      return;
    }
    const ordered = spans.slice().sort((a, b) => {
      const order = ["parse_intent", "query_catalog", "select_product", "user_confirmation", "create_order", "process_payment", "handle_payment_failure", "checkout_request", "agent_run"];
      const ia = order.indexOf(a.name);
      const ib = order.indexOf(b.name);
      if (ia !== -1 && ib !== -1) return ia - ib;
      return new Date(a.start_time) - new Date(b.start_time);
    });
    ordered.forEach((sp) => {
      const row = document.createElement("div");
      row.className = "trace-row " + (sp.status === "error" ? "error" : sp.status === "running" ? "running" : "completed");
      const t = new Date(sp.start_time).toLocaleTimeString("en-IN", { hour12: false });
      row.innerHTML =
        `<span class="trace-status">${sp.status === "error" ? "\u2715" : sp.status === "running" ? "\u25CF" : "\u2713"}</span>` +
        `<span class="trace-name">${esc(sp.name)}</span>` +
        `<span class="trace-time">${t}</span>`;
      traceLog.appendChild(row);
    });
    scrollTrace();
  }

  function scrollTrace() {
    traceLog.scrollTop = traceLog.scrollHeight;
  }

  function renderSku(data) {
    if (!data || !data.product_name) {
      skuCard.innerHTML = `<div class="sku-empty">No item selected yet.</div>`;
      return;
    }
    skuCard.innerHTML =
      `<div class="sku-head"><span class="sku-emoji">${esc(data.product_emoji || "\u25C6")}</span><span>${esc(data.product_name)}</span></div>` +
      `<div class="sku-under">${esc(data.product_summary || "")}</div>` +
      `<div class="sku-price">${data.amount ? rupee(data.amount) : ""}</div>`;
  }

  function renderPay(data) {
    if (!data || !data.payment_link) {
      if (data && data.success === false) {
        payBox.innerHTML =
          `<div><span class="pay-status error">${esc(data.payment_status || "failed")}</span></div>` +
          `<div class="pay-meta"><span>${esc(data.error || "Payment failed")}</span></div>`;
        return;
      }
      if (!data || (!data.order_id && !data.payment_link && data.stage !== "done")) {
        payBox.innerHTML = `<div class="pay-empty">Select an item to generate a payment link.</div>`;
        return;
      }
      payBox.innerHTML = `<div class="pay-empty">Awaiting payment link.</div>`;
      return;
    }
    payBox.innerHTML =
      `<div><span class="pay-status success">${esc(data.payment_status || "success")}</span></div>` +
      `<div class="pay-meta">` +
      (data.order_id ? `<span>order ${esc(data.order_id)}</span>` : "") +
      (data.amount ? `<span>${rupee(data.amount)}</span>` : "") +
      `</div>` +
      `<div class="pay-link-gen">` +
      `<span class="pay-url">${esc(data.payment_link)}</span>` +
      `<a class="open-link" href="${esc(data.payment_link)}" target="_blank" rel="noopener">Pay</a>` +
      `</div>`;
  }

  async function fetchTrace(traceId) {
    if (!traceId || traceId === lastTraceId) return;
    lastTraceId = traceId;
    laminarLink.href = `https://laminar.sh/project/${LAMINAR_PROJECT}/traces?query=${encodeURIComponent(traceId)}`;
    try {
      const r = await fetch(`/traces/${encodeURIComponent(traceId)}`);
      if (r.ok) {
        const data = await r.json();
        renderTrace(data.spans);
      }
    } catch (e) {
      /* trace view is best-effort */
    }
  }

  async function send(text) {
    if (busy || !text || !text.trim()) return;
    const msg = text.trim();
    busy = true;
    sendBtn.disabled = true;
    chatInput.value = "";
    addUserMsg(msg);
    try {
      const r = await fetch(`/chat/${encodeURIComponent(sessionId)}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: msg }),
      });
      const data = await r.json();
      handleReply(data);
    } catch (e) {
      addAgentMsg("Something went wrong reaching the agent. Is the server running?");
    } finally {
      busy = false;
      sendBtn.disabled = false;
      chatInput.focus();
    }
  }

  function handleReply(data) {
    setStage(data.stage);
    lastTraceId = null;
    fetchTrace(data.trace_id);

    if (data.stage === "select" && data.options && data.options.length) {
      addAgentMsg(data.message);
      speak(data.message + " Pick a variant from the list.");
      addVariantOptions(data.options);
      renderSku(null);
      renderPay(null);
      return;
    }

    if (data.stage === "confirm") {
      addAgentMsg(data.message);
      speak(data.message);
      renderSku(data);
      renderPay(null);
      scheduleAutoConfirm();
      return;
    }

    addAgentMsg(data.message);
    speak(data.message);

    if (data.stage === "done") {
      if (data.success) {
        renderSku(data);
        renderPay(data);
        addMetaNote(`Payment ${data.payment_status} · order ${data.order_id}`, false, data.order_id);
      } else {
        renderSku(data);
        renderPay(data);
        addMetaNote(`Payment failed → ${data.error}`, true);
      }
      return;
    }

    renderSku(data);
    renderPay(data);
  }

  function scheduleAutoConfirm() {
    clearTimeout(autoConfirmTimer);
    autoConfirmTimer = setTimeout(() => send("yes"), 900);
  }

  async function startSession() {
    try {
      const r = await fetch("/chat");
      const data = await r.json();
      sessionId = data.session_id;
      addAgentMsg(data.message);
      setStage("browse");
      renderTrace(null);
    } catch (e) {
      addAgentMsg("Could not start a session — is the server running?");
    }
  }

  /* ---- Quick scenarios ---- */
  const SCENARIOS = {
    iphone: "Place an order for iPhone 16, show me the color options",
    bandage: "I need a crepe bandage for a sprain",
    cake: "Order a chocolate ice cream cake for a birthday",
    failure: "Buy an iPhone 16 in Natural 128GB using my card",
  };

  $$(".q-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      if (busy) return;
      clearTimeout(autoConfirmTimer);
      renderSku(null);
      renderPay(null);
      // new session per scenario for a clean demo
      fetch("/chat")
        .then((r) => r.json())
        .then((d) => {
          sessionId = d.session_id;
          chatLog.innerHTML = "";
          addAgentMsg(d.message);
          setStage("browse");
          send(SCENARIOS[chip.dataset.scenario]);
        });
    });
  });

  /* ---- events ---- */
  sendBtn.addEventListener("click", () => send(chatInput.value));
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send(chatInput.value);
  });

  micBtn.addEventListener("click", startMic);
  voiceBtn.addEventListener("click", toggleVoice);

  catBtn.addEventListener("click", async () => {
    const open = catalog.classList.toggle("open");
    catBtn.textContent = open ? "Hide catalog" : "Browse catalog";
    if (open && !catGroups.dataset.loaded) {
      catLoading.classList.remove("hidden");
      try {
        const r = await fetch("/catalog");
        const groups = await r.json();
        renderCatalog(groups);
        catGroups.dataset.loaded = "1";
      } finally {
        catLoading.classList.add("hidden");
      }
    }
  });

  function renderCatalog(groups) {
    catGroups.innerHTML = "";
    Object.keys(groups).forEach((cat) => {
      const sec = document.createElement("div");
      sec.className = "cat-group";
      const items = groups[cat]
        .map((p) => {
          const emoji = p.emoji ? `<span class="emi">${esc(p.emoji)}</span>` : `<span class="emi"></span>`;
          return `<div class="cat-item"><span>${emoji}${esc(p.name)}</span><span class="pr">${rupee(p.price)}</span></div>`;
        })
        .join("");
      sec.innerHTML = `<h3>${esc(cat)}</h3>${items}`;
      catGroups.appendChild(sec);
    });
  }

  startSession();
})();
