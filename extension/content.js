/**
 * Ultrasound Voice AI — Content Script
 * 注入PACS页面: 浮动侧边栏 + 录音 + API调用 + DOM回填
 */

(async function () {
  "use strict";

  // 避免二次注入
  if (document.getElementById("ultrasound-ai-sidebar")) return;

  // ========== API Config ==========
  const { apiUrl } = await chrome.storage.local.get("apiUrl");
  const API_BASE = apiUrl || "http://localhost:8800";

  // ========== State ==========
  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;
  let lastResult = null;

  // ========== DOM: Sidebar ==========
  const sidebar = document.createElement("div");
  sidebar.id = "ultrasound-ai-sidebar";
  sidebar.innerHTML = `
    <div class="header">
      <h2>Ultrasound AI Assistant</h2>
      <button class="toggle-btn" id="ua-toggle">Collapse</button>
    </div>
    <div class="status-bar">
      <div class="status-dot" id="ua-status-dot"></div>
      <span id="ua-status-text">Ready</span>
    </div>
    <div class="exam-info" id="ua-exam-info">
      Detected: <b id="ua-exam-type">Unknown</b>
    </div>
    <div class="controls">
      <button class="btn btn-record" id="ua-record-btn">Record</button>
      <button class="btn btn-send" id="ua-send-btn" disabled>Send to AI</button>
    </div>
    <button class="btn btn-inject" id="ua-inject-btn" disabled>Inject into PACS Fields</button>
    <div class="log-area" id="ua-log"></div>
  `;
  document.body.appendChild(sidebar);

  // ========== DOM: Toggle Tab (when collapsed) ==========
  const toggleTab = document.createElement("button");
  toggleTab.className = "toggle-tab";
  toggleTab.innerHTML = "AI";
  document.body.appendChild(toggleTab);

  // ========== DOM Refs ==========
  const recordBtn = document.getElementById("ua-record-btn");
  const sendBtn = document.getElementById("ua-send-btn");
  const injectBtn = document.getElementById("ua-inject-btn");
  const statusDot = document.getElementById("ua-status-dot");
  const statusText = document.getElementById("ua-status-text");
  const examTypeEl = document.getElementById("ua-exam-type");
  const logArea = document.getElementById("ua-log");
  const toggleBtn = document.getElementById("ua-toggle");

  // ========== Auto-detect exam type ==========
  function detectExamType() {
    const selectors = [
      "#exam_item", "#exam_type", "#examType", "#exam-part", "#examPart",
      "[name='exam_type']", "[name='examType']", "[data-exam]",
      ".exam-type", ".exam_item", "#jcbw", "#JCBW",
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) {
        const val = el.value || el.textContent || el.innerText || "";
        const clean = val.trim();
        if (clean && clean.length > 1 && clean.length < 50) {
          return clean;
        }
      }
    }
    return "腹部超声";
  }

  const detectedExam = detectExamType();
  examTypeEl.textContent = detectedExam;

  // 监控 exam_type 变化
  const examObserver = new MutationObserver(() => {
    const newExam = detectExamType();
    if (newExam !== examTypeEl.textContent) {
      examTypeEl.textContent = newExam;
      addLog("info", `Exam type changed: ${newExam}`);
    }
  });
  examObserver.observe(document.body, { subtree: true, attributes: true, characterData: true });

  // ========== UI Helpers ==========
  function setStatus(state, text) {
    statusDot.className = "status-dot " + state;
    statusText.textContent = text;
  }

  function addLog(type, message, detail) {
    const entry = document.createElement("div");
    entry.className = `log-entry ${type}`;
    const time = new Date().toLocaleTimeString();
    entry.innerHTML = `[${time}] ${message}`;
    if (detail) {
      const pre = document.createElement("pre");
      pre.textContent = typeof detail === "string" ? detail : JSON.stringify(detail, null, 2);
      entry.appendChild(pre);
    }
    logArea.appendChild(entry);
    logArea.scrollTop = logArea.scrollHeight;
  }

  // ========== Recording ==========
  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      audioChunks = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };

      mediaRecorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        if (audioChunks.length > 0) {
          sendBtn.disabled = false;
          setStatus("connected", "Recording complete");
          addLog("success", `Recording stopped. ${audioChunks.length} chunks, ready to send.`);
        }
      };

      mediaRecorder.start(1000);
      isRecording = true;
      recordBtn.textContent = "Stop";
      recordBtn.classList.add("recording");
      setStatus("recording", "Recording...");
      addLog("info", "Recording started...");
    } catch (e) {
      addLog("error", "Microphone access denied", e.message);
    }
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
    isRecording = false;
    recordBtn.textContent = "Record";
    recordBtn.classList.remove("recording");
  }

  recordBtn.addEventListener("click", () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  });

  // ========== Send to AI ==========
  sendBtn.addEventListener("click", async () => {
    if (audioChunks.length === 0) {
      addLog("error", "No audio recorded. Please record first.");
      return;
    }

    setStatus("processing", "Calling AI...");
    sendBtn.disabled = true;
    injectBtn.disabled = true;

    const blob = new Blob(audioChunks, { type: "audio/webm" });
    const formData = new FormData();
    formData.append("audio_file", blob, "recording.webm");

    const ctx = {
      gender: detectGender(),
      age: detectAge(),
      exam_type: detectExamType(),
    };
    formData.append("patient_context", JSON.stringify(ctx));

    addLog("info", `Sending to ${API_BASE}/api/v1/transcribe...`);

    try {
      const resp = await fetch(`${API_BASE}/api/v1/transcribe`, {
        method: "POST",
        body: formData,
      });
      const data = await resp.json();

      if (data.code === 200 && data.data) {
        lastResult = data.data;
        injectBtn.disabled = false;
        setStatus("connected", data.data.degraded ? "Done (degraded)" : "Done");

        const hintCount = (data.data.study_hint || []).length;
        addLog("success",
          `AI complete! Method: ${data.data.method}, Template: ${data.data.template_used}`,
          `Study See: ${stripHtml(data.data.study_see || "").substring(0, 200)}...\n` +
          `Hints: ${hintCount} items\n` +
          `Warnings: ${(data.data.warnings || []).join("; ") || "none"}\n` +
          `Time: ${data.data.elapsed_ms}ms`
        );

        // 自动注入
        autoInject();
      } else {
        addLog("error", `API error: ${data.msg || "unknown"}`);
        setStatus("connected", "Error");
      }
    } catch (e) {
      addLog("error", "Network error", e.message);
      setStatus("connected", "Error");
    }

    sendBtn.disabled = false;
    audioChunks = [];
  });

  // ========== Inject into PACS ==========
  function autoInject() {
    if (!lastResult) return;
    addLog("info", "Auto-injecting into PACS fields...");

    // 映射关系: JSON key → HTML element selector
    const fieldMap = {
      "liver_size": ["#input_liver_size", "#liver_size", "[name='liver_size']"],
      "liver_echo": ["#input_liver_echo", "#liver_echo", "[name='liver_echo']"],
      "liver_shape": ["#input_liver_shape", "#liver_shape"],
      "gallbladder_size": ["#input_gallbladder_size", "#gallbladder_size", "[name='gall_size']"],
      "gallbladder_wall": ["#input_gallbladder_wall", "#gallbladder_wall", "[name='gall_wall']"],
      "gallbladder_content": ["#input_gallbladder_content", "#gallbladder_content"],
      "pancreas": ["#input_pancreas", "#pancreas"],
      "spleen": ["#input_spleen", "#spleen"],
      "kidney_left": ["#input_kidney_left", "#kidney_left"],
      "kidney_right": ["#input_kidney_right", "#kidney_right"],
      "prostate": ["#input_prostate", "#prostate"],
      "uterus": ["#input_uterus", "#uterus"],
      "ovary_left": ["#input_ovary_left", "#ovary_left"],
      "ovary_right": ["#input_ovary_right", "#ovary_right"],
      "thyroid_left": ["#input_thyroid_left", "#thyroid_left"],
      "thyroid_right": ["#input_thyroid_right", "#thyroid_right"],
      "breast_left": ["#input_breast_left", "#breast_left"],
      "breast_right": ["#input_breast_right", "#breast_right"],
      "bi_rads": ["#input_bi_rads", "#bi_rads"],
      "other_findings": ["#input_other_findings", "#other_findings", "#otherFindings"],
      "study_see": ["#study_see", "#studySee", "#input_study_see", "[name='study_see']"],
      "study_hint": ["#study_hint", "#studyHint", "#input_study_hint"],
      "recommendation": ["#recommendation", "#input_recommendation"],
    };

    const studySee = stripHtml(lastResult.study_see || "");
    const hints = (lastResult.study_hint || []).map((h) => `${h.rank}. ${h.diagnosis} (${h.icd10})`).join("\n");

    let injected = 0;
    let errors = 0;

    // 注入整体 report
    injectField(fieldMap["study_see"], studySee);
    injectField(fieldMap["study_hint"], hints);
    injectField(fieldMap["recommendation"], lastResult.recommendation || "");

    // 注入 other_findings
    injectField(fieldMap["other_findings"], studySee);

    addLog("success", `Injected structured report`, `study_see: ${studySee.substring(0, 100)}...\nHints: ${hints}`);
  }

  function injectField(selectors, value) {
    if (!selectors || !value) return;
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) {
        if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
          el.value = value;
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
          // Visual feedback: highlight then fade (adopted from ultrasound-voice-report)
          el.style.backgroundColor = "#ecfdf5";
          el.style.transition = "background-color 1.5s ease";
          setTimeout(() => { el.style.backgroundColor = ""; }, 1500);
        } else {
          el.textContent = value;
        }
        return true;
      }
    }
    return false;
  }

  injectBtn.addEventListener("click", autoInject);

  // ========== Helpers ==========
  function stripHtml(html) {
    const tmp = document.createElement("div");
    tmp.innerHTML = html;
    return tmp.textContent || tmp.innerText || "";
  }

  function detectGender() {
    const sels = ["#gender", "#patient_gender", "[name='gender']", "#xb", "#XB"];
    for (const sel of sels) {
      const el = document.querySelector(sel);
      if (el) {
        const v = (el.value || el.textContent || "").trim();
        if (v === "男" || v === "male") return "男";
        if (v === "女" || v === "female") return "女";
      }
    }
    return "";
  }

  function detectAge() {
    const sels = ["#age", "#patient_age", "[name='age']", "#nl", "#NL"];
    for (const sel of sels) {
      const el = document.querySelector(sel);
      if (el) {
        const v = parseInt(el.value || el.textContent) || null;
        if (v) return v;
      }
    }
    return null;
  }

  // ========== Toggle ==========
  let collapsed = false;
  toggleBtn.addEventListener("click", () => {
    collapsed = !collapsed;
    sidebar.classList.toggle("collapsed", collapsed);
    toggleTab.style.display = collapsed ? "block" : "none";
    toggleBtn.textContent = collapsed ? "Expand" : "Collapse";
  });

  // ========== Message Listener (from popup) ==========
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.action === "toggleRecord") {
      if (isRecording) stopRecording();
      else startRecording();
    } else if (msg.action === "injectToPacs") {
      autoInject();
    } else if (msg.action === "reset") {
      audioChunks = [];
      lastResult = null;
      isRecording = false;
      recordBtn.textContent = "Record";
      recordBtn.classList.remove("recording");
      sendBtn.disabled = true;
      injectBtn.disabled = true;
      setStatus("connected", "Ready");
      addLog("info", "Reset complete");
    }
    sendResponse({ ok: true });
  });

  // ========== Init ==========
  setStatus("connected", "Ready");
  addLog("info", `Ultrasound AI Assistant loaded. Detected exam: ${detectedExam}`);
  addLog("info", `API: ${API_BASE}`);
})();
