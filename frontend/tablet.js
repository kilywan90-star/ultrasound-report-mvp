/**
 * 平板实时听写 - 业务逻辑
 * 整体设计：
 * - 浏览器 Web Speech API 实时语音识别
 * - 每2秒增量文本自动送 /api/structure 预览（不写库）
 * - 点击确认后走工作站 /generate-report 入库
 * - 独立文件，不依赖其他 JS
 */

(function () {
  "use strict";

  // ===== 状态 =====
  const State = {
    recognition: null,
    isListening: false,
    restartTimer: null,
    finalText: '',
    interimText: '',
    debounceTimer: null,
    currentResult: null,
    currentSession: null,
    patients: [],
    selectedPatient: null,
    checkInterval: null,
  };

  // ===== DOM 引用 =====
  const $ = (id) => document.getElementById(id);

  // ===== 初始化 =====
  function init() {
    bindEvents();
    loadQueue();
    checkHTTPS();
    // 时钟
    tickTabletClock();
    setInterval(tickTabletClock, 1000);
  }

  function tickTabletClock() {
    const el = document.getElementById('tabletClock');
    if (!el) return;
    const now = new Date();
    el.textContent = now.toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'});
  }

  function checkHTTPS() {
    const el = $('httpsWarn');
    if (!window.isSecureContext && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
      el.style.display = 'block';
    } else {
      el.style.display = 'none';
    }
  }

  function bindEvents() {
    $('listenBtn').addEventListener('click', toggleListening);
    $('confirmBtn').addEventListener('click', confirmReport);
    $('clearBtn').addEventListener('click', clearAll);
    $('patientSelect').addEventListener('change', onPatientSelect);
  }

  // ===== 加载患者队列 =====
  async function loadQueue() {
    const sel = $('patientSelect');
    try {
      const resp = await fetch('/api/workstation/queue?status=' + encodeURIComponent('待检') + '&limit=50');
      const data = await resp.json();
      State.patients = data.patients || [];
      sel.innerHTML = '<option value="">请选择患者</option>';
      State.patients.forEach(p => {
        sel.innerHTML += `<option value="${p.id}">${p.name} ${p.gender||''} ${p.age||''}岁 - ${p.exam_type||''}</option>`;
      });
      renderPatientCards();
    } catch (err) {
      sel.innerHTML = '<option>加载失败</option>';
    }
  }

  async function onPatientSelect() {
    const id = parseInt($('patientSelect').value);
    if (!id) { clearPatient(); return; }
    const patient = State.patients.find(p => p.id === id);
    if (!patient) return;
    State.selectedPatient = patient;
    // 创建或恢复当天会话
    try {
      const resp = await fetch('/api/workstation/sessions', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          patient_id: id,
          doctor: '',
          exam_type: patient.exam_type || '超声',
          exam_part: patient.exam_part || '',
        }),
      });
      const data = await resp.json();
      State.currentSession = data.session;
      $('patientInfo').textContent = `${patient.name} ${patient.gender||''} ${patient.age||''}岁 | ${patient.exam_type||''}`;
      $('sessionStatus').textContent = `会话：${data.session.status}`;
      $('listenBtn').disabled = false;
      $('clearBtn').disabled = false;
    } catch (err) {
      alert('创建会话失败');
    }
  }

  function renderPatientCards() {
    const el = $('patientCards');
    if (!el) return;
    if (!State.patients.length) {
      el.innerHTML = '<div style="font-size:16px;color:var(--muted);padding:8px 0">暂无待检患者。可在医生工作站生成模拟患者。</div>';
      return;
    }
    const selectedId = State.selectedPatient?.id;
    el.innerHTML = State.patients.map(p => `
      <div class="patient-card${Number(p.id) === Number(selectedId) ? ' on' : ''}" data-id="${p.id}">
        <div class="pc-name">${escapeHtml(p.name || '-')}</div>
        <div class="pc-meta">${escapeHtml(p.gender || p.sex || '-')} ${p.age || '-'}岁 | ${escapeHtml(p.exam_type || '-')}</div>
        <div class="pc-meta">${escapeHtml(p.department || p.dept_name || '-')}</div>
        <div class="pc-tag">${escapeHtml(p.payment_status || '已缴费')}</div>
      </div>`).join('');
    document.querySelectorAll('.patient-card').forEach(card => {
      card.addEventListener('click', () => selectPatientById(Number(card.dataset.id)));
    });
  }

  async function selectPatientById(id) {
    const patient = State.patients.find(p => p.id === id);
    if (!patient) return;
    $('patientSelect').value = id;
    await onPatientSelect();
    renderPatientCards();
  }

  function clearPatient() {
    State.selectedPatient = null;
    State.currentSession = null;
    State.finalText = '';
    State.interimText = '';
    $('patientInfo').textContent = '未选择';
    $('sessionStatus').textContent = '';
    $('listenBtn').disabled = true;
    $('clearBtn').disabled = true;
    stopListening();
    clearDisplay();
    renderPatientCards();
  }

  // ===== 语音识别 =====
  function toggleListening() {
    if (State.isListening) {
      stopListening();
    } else {
      startListening();
    }
  }

  function startListening() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('浏览器不支持语音识别。请使用 Chrome 或 Edge，并通过 HTTPS 访问。');
      return;
    }
    if (!window.isSecureContext && location.hostname !== 'localhost') {
      alert('语音识别需要 HTTPS。\n请访问 https://47.109.151.238/tablet.html');
      return;
    }

    State.finalText = '';
    State.interimText = '';
    State.recognition = new SpeechRecognition();
    State.recognition.lang = 'zh-CN';
    State.recognition.continuous = true;
    State.recognition.interimResults = true;
    State.recognition.maxAlternatives = 1;

    State.recognition.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) {
          State.finalText += processVoiceCommand(t);
        } else {
          interim += t;
        }
      }
      State.interimText = interim;
      renderText();
      schedulePreview();
    };

    State.recognition.onerror = (e) => {
      if (e.error !== 'no-speech') {
        console.error('语音错误:', e.error);
        UIStatus('语音错误: ' + e.error, 'error');
        if (e.error === 'not-allowed') {
          alert('麦克风权限被拒绝。请在浏览器地址栏左侧点击🔒，开启麦克风权限。');
          stopListening();
        }
      }
    };

    State.recognition.onend = () => {
      if (State.isListening && !State.restartTimer) {
        State.restartTimer = setTimeout(() => {
          State.restartTimer = null;
          try {
            if (State.isListening) State.recognition.start();
          } catch (_) {}
        }, 200);
      } else {
        setListenUI(false);
      }
    };

    State.recognition.start();
    State.isListening = true;
    setListenUI(true);
    UIStatus('🎤 监听中...', 'listening');
  }

  function stopListening() {
    State.isListening = false;
    if (State.restartTimer) {
      clearTimeout(State.restartTimer);
      State.restartTimer = null;
    }
    if (State.recognition) {
      try { State.recognition.stop(); } catch (_) {}
      State.recognition = null;
    }
    setListenUI(false);
    UIStatus('已暂停', '');
    renderText();
    // 最后做一次预览
    doPreview();
  }

  function setListenUI(on) {
    const btn = $('listenBtn');
    if (on) {
      btn.textContent = '⏹ 停止监听';
      btn.className = 'btn-danger';
    } else {
      btn.textContent = '🎤 开始监听';
      btn.className = 'btn-primary';
    }
  }

  function processVoiceCommand(text) {
    const t = (text || '').trim();
    if (!t) return '';
    if (/清空|重来|重新开始/.test(t)) {
      clearDisplay();
      UIStatus('已按语音指令清空', '');
      return '';
    }
    if (/上一句不要|刚才不要|这句不要|删除上一句/.test(t)) {
      removeLastSentence();
      UIStatus('已删除上一句', '');
      return '';
    }
    if (/确认报告|生成报告|保存报告/.test(t)) {
      setTimeout(confirmReport, 300);
      return '';
    }
    return t;
  }

  function removeLastSentence() {
    const parts = State.finalText.split(/([。！？!?])/);
    if (parts.length <= 2) {
      State.finalText = '';
      return;
    }
    parts.splice(-2);
    State.finalText = parts.join('');
  }

  // ===== 显示文本 =====
  function renderText() {
    const el = $('recognizedText');
    if (State.finalText || State.interimText) {
      el.innerHTML = `<span class="final">${escapeHtml(State.finalText)}</span><span class="interim">${escapeHtml(State.interimText)}</span>`;
    } else {
      el.textContent = '等待语音输入...';
    }
    const el2 = $('finalOnly');
    if (el2) el2.textContent = State.finalText || '(等待语音输入)';
  }

  // ===== 节流调用 /api/structure 预览 =====
  function schedulePreview() {
    if (State.debounceTimer) clearTimeout(State.debounceTimer);
    State.debounceTimer = setTimeout(() => {
      State.debounceTimer = null;
      doPreview();
    }, 2000);
  }

  async function doPreview() {
    const text = (State.finalText || '').trim();
    if (!text) return;
    const examType = State.selectedPatient?.exam_type || '腹部超声';
    try {
      const resp = await fetch('/api/structure', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text, exam_type: examType}),
      });
      const data = await resp.json();
      if (data.success) {
        State.currentResult = data;
        renderPreview(data);
      }
    } catch (_) {
      // 静默跳过
    }
  }

  function renderPreview(d) {
    const report = d.report || {};
    const see = stripHtml(report.study_see || '');
    const hints = (report.study_hint || []).filter(h => h.checked !== false);
    const rec = report.recommendation || '';

    $('previewSite').textContent = (d.sources?.A_asr || '').slice(0, 60) ? '分析中' : '-';
    $('previewTemplate').textContent = d.template_used || '-';
    const conf = d.confidence || 0;
    const confPct = Math.round(conf * 100);
    const confColor = conf >= 0.8 ? '#34d399' : conf >= 0.6 ? '#fb923c' : '#f87171';
    $('previewConfidence').innerHTML = `<span style="color:${confColor};font-weight:bold;font-size:24px">${confPct}%</span>`;

    $('previewSee').textContent = see || '-';
    $('previewHint').textContent = hints.map(h => h.diagnosis || h).join('；') || '-';
    $('previewRec').textContent = rec || '-';

    // 源头信息
    const src = d.sources?.A_asr || '';
    $('previewSource').textContent = src ? src.slice(0, 100) : '-';
  }

  function clearDisplay() {
    State.finalText = '';
    State.interimText = '';
    State.currentResult = null;
    $('recognizedText').textContent = '等待语音输入...';
    $('finalOnly').textContent = '(等待语音输入)';
    ['previewSite','previewTemplate','previewSee','previewHint','previewRec','previewSource'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = '-';
    });
    $('previewConfidence').textContent = '--';
  }

  function clearAll() {
    if (State.isListening) stopListening();
    clearDisplay();
    UIStatus('已清空', '');
  }

  // ===== 确认生成报告 =====
  async function confirmReport() {
    const text = (State.finalText || '').trim();
    if (!text) { UIStatus('没有可确认的文本', 'error'); return; }
    if (!State.currentSession) { UIStatus('请先选择患者', 'error'); return; }
    if (State.isListening) stopListening();
    UIStatus('⏳ 生成报告中...', 'listening');

    try {
      const resp = await fetch('/api/structure', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          text,
          exam_type: State.selectedPatient?.exam_type || '腹部超声',
          patient_id: String(State.selectedPatient?.id || ''),
          patient_name: State.selectedPatient?.name || '',
          patient_gender: State.selectedPatient?.gender || State.selectedPatient?.sex || '',
          patient_age: State.selectedPatient?.age || 0,
          clinical_diag: State.selectedPatient?.clinical_diag || '',
        }),
      });
      const d = await resp.json();
      if (d.success) {
        State.currentResult = d;
        renderPreview(d);
        UIStatus('✅ 报告已生成（预览模式）', '');
        $('confirmResult').textContent = '报告已生成，可回到医生工作站完成保存/发送。';
        $('confirmResult').className = 'alert-success';
      } else {
        UIStatus('生成失败', 'error');
      }
    } catch (err) {
      UIStatus('出错: ' + err.message, 'error');
    }
  }

  // ===== UI 辅助 =====
  function UIStatus(msg, type) {
    const el = $('statusMsg');
    el.textContent = msg;
    el.className = 'status-msg';
    if (type) el.classList.add('status-' + type);
  }

  function stripHtml(h) {
    const d = document.createElement('div');
    d.innerHTML = h;
    return d.textContent || d.innerText || '';
  }

  function escapeHtml(t) {
    const e = document.createElement('span');
    e.textContent = t;
    return e.innerHTML;
  }

  // ===== 启动 =====
  document.addEventListener('DOMContentLoaded', init);
})();