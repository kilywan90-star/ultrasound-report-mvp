/**
 * Ultrasound Voice AI — Content Script v3.0 (Foot Pedal Edition)
 * USB脚踏开关 F4 → Toggle状态机 → TTS患者播报 → 录音 → API → PACS回填
 *
 * 黄金交互时序:
 *   踩下F4 → TTS播报'{姓名}{性别}' → Beep → 开始录音
 *   再踩F4 → Double-Beep → 停止录音 → 发送API → 回填PACS
 *
 * 安全:
 *   - TTS播放时不录音(防声学串扰)
 *   - 播放中再踩F4 = 取消(红色提示)
 *   - 自动抓取PACS患者信息
 */

(async function () {
  "use strict";

  if (document.getElementById("ultrasound-ai-sidebar")) return;

  const { apiUrl } = await chrome.storage.local.get("apiUrl");
  const API_BASE = apiUrl || "http://47.109.151.238:8800";

  // ========== Three-State Toggle Machine ==========
  const STATE = { IDLE: "idle", TTS: "tts", RECORDING: "recording", PROCESSING: "processing" };
  let currentState = STATE.IDLE;
  let mediaRecorder = null;
  let audioChunks = [];
  let lastResult = null;
  let currentPatient = { name: "", gender: "", age: null, examType: "", patientId: "" };

  // ========== Audio: Beep Generator ==========
  function playBeep(freq, duration, count = 1) {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    let delay = 0;
    for (let i = 0; i < count; i++) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.frequency.value = freq;
      osc.type = "square";
      gain.gain.value = 0.08;
      const startTime = ctx.currentTime + delay;
      osc.start(startTime);
      osc.stop(startTime + duration);
      delay += 0.15;
    }
  }

  function startBeep() { playBeep(880, 0.1, 1); }
  function stopBeep() { playBeep(440, 0.15, 2); }

  // ========== TTS: Patient Verification ==========
  function speakPatientVerification(name, gender, examType) {
    return new Promise((resolve) => {
      const text = `当前患者: ${name}, ${gender}, ${examType}，请确认。`;
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "zh-CN";
      utterance.rate = 0.95;
      utterance.onend = () => {
        setTimeout(resolve, 150);
      };
      utterance.onerror = () => resolve();
      window.speechSynthesis.speak(utterance);
    });
  }

  // ========== DOM: Sidebar ==========
  const sidebar = document.createElement("div");
  sidebar.id = "ultrasound-ai-sidebar";
  sidebar.innerHTML = `
    <div class="header">
      <h2>US Voice AI</h2>
      <span class="foot-indicator" id="ua-foot-icon" title="F4脚踏开关">foot</span>
      <button class="toggle-btn" id="ua-toggle">-</button>
    </div>
    <div class="status-bar">
      <div class="status-dot" id="ua-status-dot"></div>
      <span id="ua-status-text">踩脚踏(F4)开始</span>
    </div>
    <div class="patient-info" id="ua-patient-info">
      <div class="pi-row"><b id="ua-pi-name">---</b> <span id="ua-pi-gender"></span> <span id="ua-pi-age"></span></div>
      <div class="pi-row"><small id="ua-pi-exam"></small></div>
    </div>
    <div class="controls">
      <button class="btn btn-record" id="ua-record-btn">Record</button>
      <button class="btn btn-send" id="ua-send-btn" disabled>Send to AI</button>
    </div>
    <button class="btn btn-inject" id="ua-inject-btn" disabled>Inject into PACS</button>
    <div class="log-area" id="ua-log"></div>
  `;
  document.body.appendChild(sidebar);

  // Toggle tab (when collapsed)
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
  const toggleBtn = document.getElementById("ua-toggle");
  const logArea = document.getElementById("ua-log");
  const piName = document.getElementById("ua-pi-name");
  const piGender = document.getElementById("ua-pi-gender");
  const piAge = document.getElementById("ua-pi-age");
  const piExam = document.getElementById("ua-pi-exam");
  const footIcon = document.getElementById("ua-foot-icon");

  // ========== Patient Detection from PACS DOM ==========
  function detectPatient() {
    const nameSels = ["#patient_name", "#name", "[name='patient_name']", "#xm", "#XM", "#brxm"];
    const genderSels = ["#gender", "#patient_gender", "[name='gender']", "#xb", "#XB"];
    const ageSels = ["#age", "#patient_age", "[name='age']", "#nl", "#NL"];
    const examSels = ["#exam_type", "#examType", "#exam_item", "[name='exam_type']", "#jcbw"];
    const idSels = ["#patient_id", "#patientId", "#outpatientNo", "[name='patient_id']", "#mzh"];

    let name = ""; for (const s of nameSels) { const el = document.querySelector(s); if (el) { name = (el.value||el.textContent||"").trim(); if (name) break; } }
    let gender = ""; for (const s of genderSels) { const el = document.querySelector(s); if (el) { const v = (el.value||el.textContent||"").trim(); if (v==="男"||v==="male") gender="男"; else if (v==="女"||v==="female") gender="女"; if (gender) break; } }
    let age = null; for (const s of ageSels) { const el = document.querySelector(s); if (el) { age = parseInt(el.value||el.textContent)||null; if (age) break; } }
    let exam = "腹部超声"; for (const s of examSels) { const el = document.querySelector(s); if (el) { exam = (el.value||el.textContent||"").trim(); if (exam && exam.length>1 && exam.length<60) break; } }
    let pid = ""; for (const s of idSels) { const el = document.querySelector(s); if (el) { pid = (el.value||el.textContent||"").trim(); if (pid) break; } }

    return { name, gender, age, examType: exam, patientId: pid || ("auto-"+Date.now()) };
  }

  function refreshPatient() {
    currentPatient = detectPatient();
    piName.textContent = currentPatient.name || "未识别";
    piGender.textContent = currentPatient.gender || "";
    piAge.textContent = currentPatient.age ? currentPatient.age+"岁" : "";
    piExam.textContent = currentPatient.examType || "";
  }

  refreshPatient();
  setInterval(refreshPatient, 3000);

  // ========== UI Helpers ==========
  function setStatus(state, text) {
    statusDot.className = "status-dot " + state;
    statusText.textContent = text;
    footIcon.className = "foot-indicator " + (currentState === STATE.RECORDING ? "active" : "");
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
    if (logArea.children.length > 50) logArea.removeChild(logArea.firstChild);
  }

  function stripHtml(html) {
    const tmp = document.createElement("div");
    tmp.innerHTML = html;
    return tmp.textContent || tmp.innerText || "";
  }

  // ========== Recording ==========
  async function startRecordingRaw() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
    audioChunks = [];
    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      if (audioChunks.length > 0) {
        sendBtn.disabled = false;
        addLog("success", `录音完毕, ${audioChunks.length} chunks`);
      }
    };
    mediaRecorder.start(1000);
    recordBtn.textContent = "Stop";
    recordBtn.classList.add("recording");
    setStatus("recording", "录音中...");
    addLog("info", "录音开始");
  }

  function stopRecordingRaw() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
    recordBtn.textContent = "Record";
    recordBtn.classList.remove("recording");
    currentState = STATE.IDLE;
    setStatus("connected", "踩脚踏(F4)继续");
    stopBeep();
  }

  // ========== F4 Foot Pedal: Toggle Handler ==========
  async function handleFootPedal() {
    refreshPatient();
    if (!currentPatient.patientId) {
      currentPatient.patientId = "PEDAL-" + Date.now();
    }

    switch (currentState) {
      case STATE.IDLE:
        // → TTS播报 → Beep → 录音
        currentState = STATE.TTS;
        setStatus("processing", "播报患者信息...");
        footIcon.classList.add("blink");
        addLog("info", `TTS播报: ${currentPatient.name} ${currentPatient.gender} ${currentPatient.examType}`);

        await speakPatientVerification(
          currentPatient.name || "未识别",
          currentPatient.gender || "",
          currentPatient.examType || ""
        );

        // Check if cancelled during TTS
        if (currentState !== STATE.TTS) return;

        footIcon.classList.remove("blink");
        startBeep();
        await new Promise(r => setTimeout(r, 200));

        currentState = STATE.RECORDING;
        await startRecordingRaw();
        break;

      case STATE.TTS:
        // Cancel during TTS playback
        window.speechSynthesis.cancel();
        currentState = STATE.IDLE;
        footIcon.classList.remove("blink");
        sidebar.classList.add("flash-red");
        setTimeout(() => sidebar.classList.remove("flash-red"), 1500);
        setStatus("connected", "已取消 — 请手动核对患者");
        addLog("warn", "脚踏取消 — TTS播放中踩停, 未录音");
        break;

      case STATE.RECORDING:
        // Stop recording
        currentState = STATE.PROCESSING;
        stopRecordingRaw();
        setStatus("processing", "正在发送AI...");
        addLog("info", "录音结束, 发送API...");

        // Auto-send to API
        if (audioChunks.length > 0) {
          await sendToApi();
        }
        currentState = STATE.IDLE;
        break;

      case STATE.PROCESSING:
        addLog("warn", "正在处理中, 请稍候...");
        break;
    }
  }

  // ========== Global F4 Listener ==========
  document.addEventListener("keydown", (event) => {
    if (event.key === "F4") {
      event.preventDefault();
      event.stopPropagation();
      handleFootPedal();
    }
  }, true);

  // ========== Send to API ==========
  async function sendToApi() {
    setStatus("processing", "Calling AI...");
    sendBtn.disabled = true; injectBtn.disabled = true;

    const blob = new Blob(audioChunks, { type: "audio/webm" });
    const formData = new FormData();
    formData.append("audio_file", blob, "recording.webm");
    formData.append("patient_context", JSON.stringify({
      patient_id: currentPatient.patientId,
      gender: currentPatient.gender || "",
      age: currentPatient.age || 0,
      exam_type: currentPatient.examType || "腹部超声",
      name: currentPatient.name || "",
    }));

    try {
      const resp = await fetch(`${API_BASE}/v1/transcribe`, {
        method: "POST",
        body: formData,
      });
      const data = await resp.json();

      if (data.code === 200 && data.data) {
        lastResult = data.data;
        injectBtn.disabled = false;
        setStatus("connected", data.data.degraded ? "Done (degraded)" : "Done");
        addLog("success",
          `AI完成: ${data.data.method}, 模板: ${data.data.template_used}`,
          `所见: ${stripHtml(data.data.study_see||"").substring(0,150)}...\n提示: ${(data.data.study_hint||[]).map(h=>h.diagnosis).join(", ")}`
        );
        autoInject();
      } else if (data.command) {
        // Voice command macro
        handleVoiceCommand(data.command);
      } else if (data.dual_mixed) {
        setStatus("connected", "混录脏数据");
        addLog("warn", `跨患者混录音频 — 不结构化不计费。${data.msg}`);
      } else {
        addLog("error", `API错误: ${data.msg||"unknown"}`);
        setStatus("connected", "Error");
      }
    } catch (e) {
      addLog("error", "网络错误", e.message);
      setStatus("connected", "Error");
    }

    sendBtn.disabled = false;
    audioChunks = [];
    currentState = STATE.IDLE;
    setStatus("connected", "踩脚踏(F4)继续");
  }

  // ========== Manual buttons ==========
  recordBtn.addEventListener("click", handleFootPedal);
  sendBtn.addEventListener("click", () => {
    if (!audioChunks.length) { addLog("error", "无录音"); return; }
    sendToApi();
  });

  // ========== Inject into PACS ==========
  function autoInject() {
    if (!lastResult) return;
    addLog("info", "自动注入PACS字段...");
    const studySee = stripHtml(lastResult.study_see || "");
    const hints = (lastResult.study_hint || []).map((h) => `${h.rank}. ${h.diagnosis} (${h.icd10})`).join("\n");

    const fieldMap = {
      study_see: ["#study_see", "#studySee", "#input_study_see", "[name='study_see']"],
      study_hint: ["#study_hint", "#studyHint", "#input_study_hint"],
      recommendation: ["#recommendation", "#input_recommendation"],
      other_findings: ["#input_other_findings", "#otherFindings"],
      bi_rads: ["#input_bi_rads", "#bi_rads"],
    };

    injectField(fieldMap["study_see"], studySee);
    injectField(fieldMap["study_hint"], hints);
    injectField(fieldMap["recommendation"], lastResult.recommendation || "");
    injectField(fieldMap["other_findings"], studySee);

    addLog("success", "PACS回填完成");
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
          el.style.backgroundColor = "#ecfdf5";
          el.style.transition = "background-color 1.5s ease";
          setTimeout(() => { el.style.backgroundColor = ""; }, 1500);
        } else {
          el.textContent = value;
        }
      }
    }
  }

  injectBtn.addEventListener("click", autoInject);

  // ========== Toggle sidebar ==========
  let collapsed = false;
  toggleBtn.addEventListener("click", () => {
    collapsed = !collapsed;
    sidebar.classList.toggle("collapsed", collapsed);
    toggleTab.style.display = collapsed ? "block" : "none";
    toggleBtn.textContent = collapsed ? "+" : "-";
  });

  // ========== Popup messages ==========
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.action === "toggleRecord") handleFootPedal();
    else if (msg.action === "injectToPacs") autoInject();
    else if (msg.action === "reset") {
      audioChunks = []; lastResult = null;
      recordBtn.textContent = "Record"; recordBtn.classList.remove("recording");
      sendBtn.disabled = true; injectBtn.disabled = true;
      setStatus("connected", "Ready"); addLog("info", "Reset");
    }
    sendResponse({ ok: true });
  });

  // ========== Voice Command Macros ==========
  function handleVoiceCommand(cmd) {
    switch (cmd) {
      case "CLEAR":
        document.querySelectorAll("input, textarea").forEach(el => {
          if (el.closest("#ultrasound-ai-sidebar")) return;
          el.value = "";
          el.dispatchEvent(new Event("input", { bubbles: true }));
        });
        addLog("success", "语音指令: 已清空所有输入框");
        break;
      case "SAVE":
        const saveBtn = document.getElementById("save_btn") || document.querySelector("[name='save']") || document.querySelector("button[type='submit']");
        if (saveBtn) { saveBtn.click(); addLog("success", "语音指令: 已触发保存"); }
        else addLog("warn", "语音指令: 未找到保存按钮");
        break;
      case "NEXT":
        const inputs = [...document.querySelectorAll("input:not([type='hidden']), textarea")].filter(el => !el.closest("#ultrasound-ai-sidebar"));
        const empty = inputs.find(el => !el.value.trim());
        if (empty) { empty.focus(); addLog("info", "语音指令: 已跳转到下一个空输入框"); }
        else addLog("info", "语音指令: 所有输入框已填满");
        break;
      case "PRINT":
        window.print();
        addLog("info", "语音指令: 已触发打印");
        break;
      default:
        addLog("info", `未知语音指令: ${cmd}`);
    }
  }

  // ========== Init ==========
  setStatus("connected", "踩脚踏(F4)开始");
  addLog("info", `US Voice AI loaded. Exam: ${currentPatient.examType}. API: ${API_BASE}`);
  addLog("info", "脚踏板(F4): 踩一下开始 → TTS播报 → Beep → 录音 → 再踩结束");

  // Ping API
  try {
    fetch(`${API_BASE}/v1/health`).then(r => r.json()).then(d => {
      addLog("success", `API在线: v${d.version} (${d.asr_available?"ASR OK":"ASR DOWN"} ${d.llm_available?"LLM OK":"LLM DOWN"})`);
    }).catch(() => addLog("warn", "API不可达"));
  } catch(e) {}
})();
