/**
 * 超声医生 - 手机版 v1.0
 * 核心流程: 患者列表 → 录音 → 识别 → 候选模板选择 → 报告预览/确认
 */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);

  const S = {
    patients: [],
    patient: null,
    session: null,
    mediaRecorder: null,
    chunks: [],
    stream: null,
    recording: false,
    startedAt: 0,
    timerId: null,
    candidates: [],
    currentResult: null,
    lastRawText: '',
    darkMode: true,
  };

  document.addEventListener('DOMContentLoaded', init);

  /* ===== Init ===== */
  async function init() {
    bindEvents();
    checkSecure();
    await loadQueue();
  }

  function bindEvents() {
    safe('refreshBtn', 'click', loadQueue);
    safe('mockBtn', 'click', seedMock);
    safe('backBtn', 'click', backToPatients);
    safe('recordBtn', 'click', toggleRecord);
    safe('candSkip', 'click', skipCandidates);
    safe('reviewCancel', 'click', backToPatients);
    safe('reviewSave', 'click', confirmReport);
    safe('themeBtn', 'click', toggleTheme);
  }

  function safe(id, evt, fn) {
    const el = $(id);
    if (el) el.addEventListener(evt, fn);
  }

  /* ===== Screen Navigation ===== */
  function show(id) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('on'));
    $(id).classList.add('on');
  }

  function setState(text, ok) {
    const badge = $('stateBadge');
    if (badge) { badge.textContent = text; badge.className = 'state-badge' + (ok ? ' active' : ''); }
  }

  /* ===== HTTPS Check ===== */
  function checkSecure() {
    const warn = document.querySelector('.https-warn');
    if (!warn) return;
    if (!window.isSecureContext && location.hostname !== 'localhost') {
      warn.style.display = 'block';
    }
  }

  /* ===== Theme ===== */
  function toggleTheme() {
    S.darkMode = !S.darkMode;
    document.body.style.background = S.darkMode
      ? 'radial-gradient(ellipse at 30% 0%,rgba(56,189,248,.08),transparent 50%),#0b1628'
      : '#f0f4fa';
    document.body.style.color = S.darkMode ? '#e8f0fe' : '#0f172a';
    $('themeBtn').textContent = S.darkMode ? '🌓' : '🌙';
  }

  /* ===== Patient List ===== */
  async function loadQueue() {
    try {
      const data = await api('GET', '/api/workstation/queue');
      const list = data.patients || data || [];
      S.patients = list;
      renderPatients(list);
      $('listTitle').textContent = `待检患者 (${list.length})`;
    } catch (e) {
      toast('加载患者列表失败', true);
    }
  }

  function renderPatients(list) {
    const grid = $('patientGrid');
    if (!grid) return;
    if (!list.length) { grid.innerHTML = '<div class="empty">暂无待检患者</div>'; return; }
    grid.innerHTML = list.map(p => {
      const name = p.name || '未知';
      const exam = p.exam_type || p.visit_dept || '超声';
      const tag = p.status_label || '待检';
      const age = p.age ? (p.age + (p.age_unit || '岁')) : '';
      const gender = p.gender || p.sex || '';
      const meta = [exam, gender, age].filter(Boolean).join(' · ');
      return `<div class="patient-card" data-id="${p.id || p.patient_id}">
        <div class="name">${esc(name)}</div>
        <div class="meta">${esc(meta)}</div>
        <div class="tag">${esc(tag)}</div>
      </div>`;
    }).join('');
    grid.querySelectorAll('.patient-card').forEach(card => {
      card.addEventListener('click', () => selectPatient(card.dataset.id));
    });
  }

  async function selectPatient(pid) {
    try {
      const p = S.patients.find(x => String(x.id || x.patient_id) === String(pid));
      if (!p) throw new Error('患者不存在');
      S.patient = p;
      const resp = await api('POST', '/api/workstation/sessions', {
        patient_id: pid,
        doctor: selectedDoctor(),
        exam_type: p.exam_type || '腹部超声',
      });
      S.session = resp.session || resp;
      enterRecord();
    } catch (e) {
      toast('选择患者失败: ' + e.message, true);
    }
  }

  function selectedDoctor() { return '管理员'; }

  async function seedMock() {
    try {
      await api('POST', '/api/workstation/sessions/seed-mock');
      toast('已添加模拟患者');
      await loadQueue();
    } catch (e) { toast('模拟失败', true); }
  }

  function backToPatients() {
    if (S.recording) stopRecord(false);
    S.patient = null; S.session = null; S.chunks = []; S.candidates = [];
    show('scList');
    setState('就绪');
    loadQueue();
  }

  /* ===== Record ===== */
  function enterRecord() {
    if (!S.patient) return;
    $('patName').textContent = S.patient.name || '患者';
    const age = S.patient.age ? (S.patient.age + (S.patient.age_unit || '岁')) : '';
    const gender = S.patient.gender || S.patient.sex || '';
    $('patMeta').textContent = [S.patient.exam_type || '超声', gender, age].filter(Boolean).join(' · ');
    $('patTag').textContent = '已缴费';
    show('scRecord');
    setState('等待录音');
  }

  async function toggleRecord() {
    if (S.recording) { await stopRecord(true); }
    else { await startRecord(); }
  }

  async function startRecord() {
    if (!S.session) { toast('请先选择患者', true); return; }
    if (!navigator.mediaDevices?.getUserMedia) { toast('浏览器不支持录音', true); return; }
    if (!window.isSecureContext && location.hostname !== 'localhost') { toast('录音需要HTTPS', true); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1,sampleRate:16000}});
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
      S.chunks = [];
      S.mediaRecorder = new MediaRecorder(stream, {mimeType});
      S.mediaRecorder.ondataavailable = e => { if (e.data && e.data.size > 0) S.chunks.push(e.data); };
      S.mediaRecorder.start(1000);
      S.recording = true; S.startedAt = Date.now();
      $('recordBtn').innerHTML = '⏹<br>停止';
      $('recordBtn').classList.add('recording');
      $('wave').style.display = 'flex';
      $('recordHint').textContent = '正在录音，点击停止';
      S.timerId = setInterval(updateTimer, 300);
      updateTimer();
      setState('录音中...', true);
    } catch (e) {
      toast('无法录音: ' + e.message, true);
    }
  }

  async function stopRecord(autoGen) {
    S.recording = false;
    clearInterval(S.timerId); S.timerId = null;
    $('wave').style.display = 'none';
    $('recordBtn').classList.remove('recording');
    $('recordBtn').innerHTML = '🎤<br>开始';
    $('recordHint').textContent = '处理中...';
    if (S.mediaRecorder && S.mediaRecorder.state !== 'inactive') {
      await new Promise(resolve => { S.mediaRecorder.onstop = resolve; S.mediaRecorder.stop(); });
    }
    if (S.stream) S.stream.getTracks().forEach(t => t.stop());
    setState('识别中...', true);
    if (autoGen) await processRecording();
  }

  function updateTimer() {
    const sec = Math.floor((Date.now() - S.startedAt) / 1000);
    const el = $('timerDisplay');
    if (el) el.textContent = `${String(Math.floor(sec/60)).padStart(2,'0')}:${String(sec%60).padStart(2,'0')}`;
  }

  /* ===== Process Recording → ASR → Candidates → Fill ===== */
  async function processRecording() {
    const blob = new Blob(S.chunks, {type:'audio/webm'});
    if (!blob || blob.size < 512) {
      toast('录音太短', true);
      enterRecord();
      return;
    }
    show('scProcess');
    $('procTitle').textContent = '识别中';
    try {
      const form = new FormData();
      form.append('file', blob, 'm.webm');
      form.append('doctor', '管理员');
      const segResp = await fetch(`/api/workstation/sessions/${S.session.id}/segments`, {method:'POST', body:form});
      if (!segResp.ok) throw new Error((await segResp.json()).detail || '识别失败');
      const segData = await segResp.json();
      if (!segData.asr?.success) throw new Error('未识别到有效语音');
      const rawText = segData.asr?.corrected_text || segData.asr?.raw_text || '';
      if (!rawText.trim()) throw new Error('未识别到有效语音');
      S.lastRawText = rawText;

      // Merge session
      await api('POST', `/api/workstation/sessions/${S.session.id}/merge`, {});

      // 获取候选模板
      $('procTitle').textContent = '获取模板';
      const candResult = await api('POST', '/api/pad/candidates', {
        text: rawText,
        exam_type: S.patient?.exam_type || '腹部超声',
        doctor_name: '管理员',
        site: S.patient?.exam_type || '腹部超声',
      });

      const cands = candResult.candidates || [];
      if (!cands.length || cands.length <= 1 || candResult.auto_fill) {
        // 自动填充
        if (cands.length) {
          await fillAndReview(cands[0].template_name, rawText);
        } else {
          await fillAndReview('', rawText);
        }
        return;
      }

      // 显示候选
      S.candidates = cands;
      showCandidates(rawText);
    } catch (e) {
      toast('处理失败: ' + e.message, true);
      enterRecord();
    }
  }

  /* ===== Candidate Selection ===== */
  function showCandidates(text) {
    $('candVoice').textContent = text.slice(0, 180);
    const grid = $('candGrid');
    grid.innerHTML = S.candidates.map((c, i) => {
      const pct = Math.round((c.score || 0) * 100);
      const scoreCls = pct >= 80 ? 'high' : pct >= 60 ? 'mid' : 'low';
      const preview = (c.description || '').replace(/<[^>]+>/g, '').slice(0, 60);
      return `<div class="cand-card" data-idx="${i}">
        <div class="top">
          <div class="name">${esc(c.template_name || '未知')}</div>
          <div class="score ${scoreCls}">${pct}%</div>
        </div>
        ${preview ? `<div class="preview">${esc(preview)}</div>` : ''}
        ${c.preference_boost > 0 ? `<div style="font-size:10px;color:var(--blue)">📌 常用 +${Math.round(c.preference_boost*100)}%</div>` : ''}
      </div>`;
    }).join('');

    grid.querySelectorAll('.cand-card').forEach(card => {
      card.addEventListener('click', () => selectCandidate(parseInt(card.dataset.idx), text));
    });

    setState(`候选 ${S.candidates.length} 个`, false);
    show('scCand');
  }

  async function selectCandidate(idx, text) {
    const cand = S.candidates[idx];
    if (!cand) return;
    // 高亮选中
    document.querySelectorAll('.cand-card').forEach((c, i) => c.classList.toggle('selected', i === idx));
    await fillAndReview(cand.template_name, text);
  }

  async function skipCandidates() {
    const text = S.lastRawText;
    if (!text) { backToPatients(); return; }
    await fillAndReview('', text);
  }

  async function fillAndReview(templateName, text) {
    if (!text) { backToPatients(); return; }
    try {
      if (templateName) {
        const result = await api('POST', '/api/pad/fill', {
          text: text,
          exam_type: S.patient?.exam_type || '腹部超声',
          doctor_name: '管理员',
          template_name: templateName,
        });
        S.currentResult = result;
        showReview(result, text, templateName);
      } else {
        const result = await api('POST', '/api/structure', {
          text: text,
          exam_type: S.patient?.exam_type || '腹部超声',
        });
        S.currentResult = result;
        showReview(result, text, '');
      }
    } catch (e) {
      toast('填充失败: ' + e.message, true);
      enterRecord();
    }
  }

  /* ===== Review ===== */
  function showReview(data, text, tpl) {
    const report = data.report || data;
    const see = (report.study_see || '').replace(/<\/?div[^>]*>/g, '').replace(/^<br\s*\/?>|^<br>/i, '');
    const hints = (report.study_hint || []).filter(h => h.checked !== false).map(h => h.diagnosis || h).join('；');
    const rec = report.recommendation || '';
    $('rSee').innerHTML = see || '(空)';
    $('rHint').innerHTML = hints || '(空)';
    $('rRec').innerHTML = rec || '(空)';
    $('reviewMethod').textContent = data.method || tpl || '?';
    setState('已生成', true);
    show('scReview');
  }

  function confirmReport() {
    toast('报告已确认', false);
    backToPatients();
  }

  /* ===== API Helper ===== */
  async function api(method, url, body) {
    const opts = {
      method,
      headers: {'Content-Type': 'application/json'},
    };
    if (body) opts.body = JSON.stringify(body);
    const resp = await fetch(url, opts);
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || '请求失败');
    return data;
  }

  /* ===== Toast ===== */
  function toast(msg, isError) {
    const el = $('toast');
    if (!el) return;
    el.textContent = msg;
    el.style.color = isError ? 'var(--red)' : 'var(--text)';
    el.classList.add('on');
    setTimeout(() => el.classList.remove('on'), 2500);
  }

  function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
})();
