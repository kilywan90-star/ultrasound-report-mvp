/**
 * 超声平板 - 合并版 v2.1
 * 修复：医生网格展示、实时听写按钮响应、主题切换
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
    appendMode: false,
    recognition: null,
    isListening: false,
    restartTimer: null,
    segmentTimer: null,
    segmentCount: 0,
    finalText: '',
    interimText: '',
    debounceTimer: null,
    currentResult: null,
    mode: 'director',
    ws: null,
    audioCtx: null,
    lastReport: null,
    lastRawText: '',
    selectedDoctor: '',
    // 候选模板状态
    candidates: [],
    selectedCandidateIdx: -1,
    selectedTemplateName: '',
    generating: false,
  };

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    bindEvents();
    tickClock(); setInterval(tickClock, 1000);
    checkSecure();
    loadQueue();
    loadDoctors();
  }

  function backToList() {
    resetSessionState();
    show('screenList');
    if (S.isListening) stopListening();
    if (S.recording) { stopRecord(false); resetRecordUI(); }
  }

  function resetSessionState() {
    S.lastRawText = '';
    S.lastReport = null;
    S.appendMode = false;
    S.chunks = [];
    S.currentResult = null;
    S.candidates = [];
    S.selectedCandidateIdx = -1;
    S.selectedTemplateName = '';
    // 清除UI上的文本
    var procText = document.getElementById('processText');
    if(procText) procText.textContent = '';
    var recognized = document.getElementById('recognizedText');
    if(recognized) recognized.textContent = '等待语音输入...';
    var finalOnly = document.getElementById('finalOnly');
    if(finalOnly) finalOnly.textContent = '(等待语音输入)';
    var tcand = document.getElementById('tabletCandidates');
    if(tcand) tcand.style.display = 'none';
    // 清理review弹窗
    var review = document.getElementById('reviewOverlay');
    if(review) review.style.display = 'none';
  }

  function bindEvents() {
    // 每个绑定单独 try-catch，防止一个失败连锁崩掉所有
    const safeBind = (id, evt, fn) => {
      try {
        const el = typeof id === 'string' ? $(id) : id;
        if (el) el.addEventListener(evt, fn);
      } catch(e) { console.warn(`bindEvents: ${id} ${evt} failed`, e); }
    };
    safeBind('refreshBtn', 'click', loadQueue);
    safeBind('mockBtn', 'click', seedMockPatients);
    safeBind('backBtn', 'click', backToList);
    safeBind('recordBtn', 'click', toggleRecord);
    safeBind('modeDirector', 'click', () => switchMode('director'));
    safeBind('modeTablet', 'click', () => switchMode('tablet'));
    safeBind('tabletListenBtn', 'click', toggleListening);
    safeBind('tabletClearBtn', 'click', clearTablet);
    safeBind('tabletDoneBtn', 'click', confirmTabletReport);
    safeBind('candSkipBtn', 'click', cancelCandidates);
    safeBind('candEditBtn', 'click', editManually);
    safeBind('themeToggle', 'click', toggleTheme);
    safeBind('daysFilter', 'change', loadQueue);
    safeBind('tabPending', 'click', () => switchPatientTab('pending'));
    safeBind('tabCompleted', 'click', () => switchPatientTab('completed'));
    const tBack = document.getElementById('tabletBackBtn');
    safeBind(tBack, 'click', backToList);
  }

  function toggleTheme() {
    const app = document.querySelector('.app');
    app.classList.toggle('light');
    const btn = $('themeToggle');
    btn.textContent = app.classList.contains('light') ? '🌙' : '🌓';
  }

  async function loadDoctors() {
    try {
      const d = await api('GET','/api/doctors');
      if (d.success && d.doctors) {
        renderDoctorGrid(d.doctors);
      } else if (d.doctors) {
        renderDoctorGrid(d.doctors);
      }
    } catch(e) {
      toast('医生列表加载失败', true);
    }
  }

  function renderDoctorGrid(doctors) {
    const grid = $('doctorGrid');
    if (!grid) return;
    // 管理员第一
    const all = ['管理员', ...doctors.filter(n => n && n !== '管理员')];
    grid.innerHTML = all.map(n =>
      `<button class="doc-chip${n === S.selectedDoctor ? ' on' : ''}" data-doctor="${n}">${n}</button>`
    ).join('');
    grid.querySelectorAll('.doc-chip').forEach(btn => {
      btn.addEventListener('click', () => selectDoctor(btn.dataset.doctor));
    });
  }

  function selectDoctor(name) {
    S.selectedDoctor = name;
    $('doctorGrid').querySelectorAll('.doc-chip').forEach(btn => {
      btn.classList.toggle('on', btn.dataset.doctor === name);
    });
  }

  function selectedDoctor() { return S.selectedDoctor || ''; }

  function switchMode(mode) {
    if (S.recording) { stopRecord(false); resetRecordUI(); }
    if (S.isListening) { stopListening(); }
    S.mode = mode;
    $('modeDirector').classList.toggle('on', mode === 'director');
    $('modeTablet').classList.toggle('on', mode === 'tablet');
    if (mode === 'director') {
      $('mainTitle').textContent = '超声平板';
      $('modeHint').textContent = '主任极简 · 选病人 录语音 自动生成';
      $('stepGuide').innerHTML = '1 选患者<br>2 开始录音<br>3 选模板 完成';
    } else {
      $('mainTitle').textContent = '超声平板';
      $('modeHint').textContent = '实时听写 · 边说边看 模板实时识别';
      $('stepGuide').innerHTML = '1 选患者<br>2 开始监听<br>3 确认报告';
    }
    show('screenList');
  }

  function checkSecure() {
    const ok = window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
    $('httpsWarn').style.display = ok ? 'none' : 'block';
  }

  function tickClock() {
    const d = new Date();
    $('clockTime').textContent = d.toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'});
    $('clockDate').textContent = d.toLocaleDateString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'});
  }

  async function api(method, path, body) {
    const opt = {method, headers: {'Content-Type': 'application/json'}};
    if (body !== undefined) opt.body = JSON.stringify(body);
    const r = await fetch(path, opt);
    if (!r.ok) { const e = await r.json().catch(()=>({detail:r.statusText})); throw new Error(e.detail||'请求失败'); }
    return r.json();
  }

  async function seedMockPatients() {
    try { const d = await api('POST','/api/workstation/mock-patients',{}); toast(`已生成 ${d.created||0} 个模拟患者`); await loadQueue(); }
    catch(e) { toast(e.message, true); }
  }

  // 标签页切换
  let currentPatientTab = 'pending';

  function switchPatientTab(tab) {
    currentPatientTab = tab;
    $('tabPending').classList.toggle('ptab-on', tab === 'pending');
    $('tabCompleted').classList.toggle('ptab-on', tab === 'completed');
    // 保持待检人数统计独立
    updateWaitingCount();
    if (tab === 'pending') loadQueue();
    else loadCompletedQueue();
  }

  async function updateWaitingCount() {
    try {
      const d = await api('GET','/api/workstation/queue?status='+encodeURIComponent('待检')+'&limit=1&days=0');
      $('statWaiting').textContent = d.total || 0;
    } catch(_) {}
  }

  async function loadCompletedQueue() {
    $('patientGrid').textContent = '加载中...';
    try {
      const d = await api('GET','/api/workstation/queue?status='+encodeURIComponent('已完成')+'&limit=200&days=0');
      S.patients = d.patients || [];
      renderPatientsCompleted();
    } catch(e) { $('patientGrid').innerHTML = `<div class="error">加载失败：${escapeHtml(e.message)}</div>`; }
  }

  function renderPatientsCompleted() {
    $('statWaiting').textContent = S.patients.length;
    $('listStatus').textContent = S.patients.length ? '选择查看报告' : '暂无已检查';
    if (!S.patients.length) { $('patientGrid').innerHTML = '<div style="font-size:20px;color:var(--muted)">暂无已检查患者</div>'; return; }
    $('patientGrid').innerHTML = S.patients.map(p =>
      `<div class="patient-card" data-id="${p.id}" style="border-color:rgba(52,211,153,.3)">
        <div class="p-card-top">
          <div class="p-name">${escapeHtml(p.name)}</div>
          <div class="p-id-badge" style="background:rgba(52,211,153,.15);color:var(--green)">#${p.id}</div>
        </div>
        <div class="p-meta">${escapeHtml(p.gender||p.sex||'-')} ${p.age||'-'}岁 | ${escapeHtml(p.exam_type||'-')}</div>
        <div class="p-meta"><span class="p-label">检查号</span> ${escapeHtml(p.exam_no||p.outpatient_id||'-')}</div>
        <div class="p-meta"><span class="p-label">开单科室</span> ${escapeHtml(p.dept_name||p.department||'-')}</div>
        <div class="p-meta"><span class="p-label">开单医生</span> ${escapeHtml(p.referring_doctor||'-')}</div>
        <div class="p-tag" style="background:rgba(52,211,153,.12);color:var(--green)">已完成</div>
      </div>`
    ).join('');
    document.querySelectorAll('.patient-card').forEach(c => c.addEventListener('click', ()=>selectPatient(Number(c.dataset.id))));
  }

  async function loadQueue() {
    $('patientGrid').textContent = '加载中...';
    try {
      const days = $('daysFilter')?.value || '0';
      const d = await api('GET','/api/workstation/queue?status='+encodeURIComponent('待检')+'&limit=200&days='+days);
      S.patients = d.patients || [];
      renderPatients();
    } catch(e) { $('patientGrid').innerHTML = `<div class="error">加载失败：${escapeHtml(e.message)}</div>`; }
  }

  function renderPatients() {
    $('statWaiting').textContent = S.patients.length;
    $('listStatus').textContent = S.patients.length ? '等待选择' : '暂无待检';
    if (!S.patients.length) { $('patientGrid').innerHTML = '<div style="font-size:20px;color:var(--muted)">暂无待检患者</div>'; return; }
    $('patientGrid').innerHTML = S.patients.map(p =>
      `<div class="patient-card" data-id="${p.id}">
        <div class="p-card-top">
          <div class="p-name">${escapeHtml(p.name)}</div>
          <div class="p-id-badge">#${p.id}</div>
        </div>
        <div class="p-meta">${escapeHtml(p.gender||p.sex||'-')} ${p.age||'-'}岁 | ${escapeHtml(p.exam_type||'-')}</div>
        <div class="p-meta"><span class="p-label">检查号</span> ${escapeHtml(p.exam_no||p.outpatient_id||'-')}</div>
        <div class="p-meta"><span class="p-label">开单科室</span> ${escapeHtml(p.dept_name||p.department||'-')}</div>
        <div class="p-meta"><span class="p-label">开单医生</span> ${escapeHtml(p.referring_doctor||'-')}</div>
        <div class="p-tag">${escapeHtml(p.payment_status||'已缴费')}</div>
      </div>`
    ).join('');
    document.querySelectorAll('.patient-card').forEach(c => c.addEventListener('click', ()=>selectPatient(Number(c.dataset.id))));
  }

  async function selectPatient(id) {
    resetSessionState();
    const p = S.patients.find(x => Number(x.id)===Number(id)); if (!p) return;
    try {
      const d = await api('POST','/api/workstation/sessions',{patient_id:p.id,doctor:selectedDoctor(),exam_type:p.exam_type||'超声',exam_part:p.exam_part||''});
      S.patient = d.patient; S.session = d.session;
      $('currentName').textContent = S.patient.name;
      $('currentMeta').textContent = `${S.patient.gender||S.patient.sex||''} ${S.patient.age||''}岁 | ${S.session.exam_type||S.patient.exam_type||''}`;
      $('currentTag').textContent = `${S.patient.department||S.patient.dept_name||''} · ${S.patient.payment_status||'已缴费'}`;
      $('liPatient').textContent = `${S.patient.name} | ${S.patient.exam_type||''}`;
      $('tabletListenBtn').disabled = false; $('tabletClearBtn').disabled = false; $('tabletDoneBtn').disabled = false;
      if (S.mode === 'director') show('screenDirector'); else show('screenTablet');
    } catch(e) { toast('创建会话失败：'+e.message, true); }
  }

  function show(id) { document.querySelectorAll('.screen').forEach(s=>s.classList.remove('on')); $(id).classList.add('on'); }

  async function toggleRecord() { if(S.recording) await stopRecord(true); else await startRecord(); }

  async function startRecord() {
    if (!S.session) return toast('请先选择患者',true);
    if (!navigator.mediaDevices?.getUserMedia) return toast('浏览器不支持录音',true);
    if (!window.isSecureContext && location.hostname !== 'localhost') return toast('录音需要HTTPS',true);
    try {
      S.stream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1,sampleRate:16000}});
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')?'audio/webm;codecs=opus':'audio/webm';
      S.chunks = []; S.mediaRecorder = new MediaRecorder(S.stream,{mimeType});
      S.mediaRecorder.ondataavailable = e => { if(e.data&&e.data.size>0) S.chunks.push(e.data); };
      S.mediaRecorder.start(1000); S.recording=true; S.startedAt=Date.now();
      $('recordBtn').innerHTML='⏹<br>停止'; $('recordBtn').classList.add('recording');
      $('wave').style.display='flex'; $('recordHint').textContent='正在录音';
      S.timerId=setInterval(updateTimer,300); updateTimer();
    } catch(e) { toast('无法录音：'+e.message,true); }
  }

  async function stopRecord(autoGenerate) {
    S.recording=false; clearInterval(S.timerId); S.timerId=null;
    $('wave').style.display='none'; $('recordBtn').classList.remove('recording');
    $('recordBtn').innerHTML='🎤<br>开始'; $('recordHint').textContent='处理中...';
    if (S.mediaRecorder && S.mediaRecorder.state !== 'inactive') {
      await new Promise(resolve => { S.mediaRecorder.onstop = resolve; S.mediaRecorder.stop(); });
    }
    if (S.stream) S.stream.getTracks().forEach(t=>t.stop());
    if (autoGenerate) await processRecording();
  }

  function updateTimer() {
    const sec = Math.floor((Date.now()-S.startedAt)/1000);
    $('timer').textContent = `${String(Math.floor(sec/60)).padStart(2,'0')}:${String(sec%60).padStart(2,'0')}`;
  }

  // ─── 核心改造：录音后 → 候选模板 → 选模板填充 → 确认 ───

  async function processRecording() {
    const blob = new Blob(S.chunks,{type:'audio/webm'});
    if (!blob||blob.size<512) { toast('录音太短',true); resetRecordUI(); show('screenDirector'); return; }
    show('screenProcess');
    try {
      $('processTitle').textContent='识别中';
      const form=new FormData(); form.append('file',blob,'pad.webm'); form.append('doctor',selectedDoctor() || '管理员');
      const segResp = await fetch(`/api/workstation/sessions/${S.session.id}/segments`,{method:'POST',body:form});
      if (!segResp.ok) throw new Error((await segResp.json()).detail||'识别失败');
      const segData = await segResp.json();
      if (!segData.asr?.success) throw new Error((segData.asr?.warnings||['未识别到有效语音']).join('；'));
      const newRaw = segData.asr?.corrected_text || segData.asr?.raw_text || '';
      if (!newRaw.trim()) throw new Error('未识别到有效语音');
      $('processText').textContent = newRaw.slice(0,150);

      // 补充一句模式
      if (S.appendMode && S.lastReport) {
        S.lastRawText += '\n' + newRaw;
        $('processTitle').textContent='合并文本';
        await api('POST',`/api/workstation/sessions/${S.session.id}/merge`,{});
        $('processTitle').textContent='补充填充';
        const suppResp = await api('POST','/api/structure',{text:S.lastRawText,exam_type:S.patient?.exam_type||'腹部超声',doctor:selectedDoctor()});
        S.appendMode = false;
        resetRecordUI();
        if (suppResp.success) {
          showReview(suppResp, S.lastRawText);
        } else {
          toast('补充填充失败', true);
          show('screenDirector');
        }
        return;
      }

      // 合并文本
      $('processTitle').textContent='合并中';
      await api('POST',`/api/workstation/sessions/${S.session.id}/merge`,{});
      S.lastRawText = newRaw;
      S.appendMode = false;

      // ── 候选模板（一次性同时获取候选并填充 Top1）──
      $('processTitle').textContent='生成报告';
      const examType = S.patient?.exam_type || '腹部超声';
      const candResult = await api('POST', '/api/pad/candidates', {
        text: newRaw,
        exam_type: examType,
        doctor_name: selectedDoctor(),
        site: examType,
      });

      if (candResult.needs_more) {
        toast('匹配不足，请补充更多描述', true);
        show('screenDirector');
        resetRecordUI();
        return;
      }

      if (candResult.auto_fill || !candResult.show_selection || candResult.candidates.length === 1) {
        // 置信度高或只有一个候选 → 直填
        const top = candResult.candidates[0];
        await fillAndShowReview(top.template_name, newRaw, examType);
        return;
      }

      // 多个候选 → 显示候选界面让医生选（不额外调LLM）
      S.candidates = candResult.candidates;
      showCandidates(newRaw);
    } catch(e) { show('screenDirector'); resetRecordUI(); toast(e.message,true); }
  }

  // ─── 候选模板选择界面 ───

  function showCandidates(rawText) {
    S.selectedCandidateIdx = -1;
    S.selectedTemplateName = '';
    S.generating = false;

    $('candPatientName').textContent = S.patient?.name || '患者';
    const meta = S.patient ? `${S.session?.exam_type || S.patient?.exam_type || '超声'} · 已识别语音` : '';
    $('candPatientMeta').textContent = meta;
    $('candVoiceText').textContent = rawText.slice(0, 200);

    const grid = $('candGrid');
    const bestScore = S.candidates[0]?.score || 0;
    grid.innerHTML = S.candidates.map((c, i) => {
      const pct = Math.round((c.score || 0) * 100);
      const scoreClass = pct >= 80 ? 'high' : pct >= 60 ? 'mid' : 'low';
      const preview = (c.description || '').replace(/<[^>]+>/g, '').slice(0, 80);
      const site = c.site || '';
      const discgroup = c.discgroup || '';
      const prefBoost = c.preference_boost || 0;
      const prefLabel = prefBoost > 0 ? `常用 +${Math.round(prefBoost * 100)}%` : '';
      return `<div class="cand-card" data-idx="${i}">
        <div class="cand-card-check">✓</div>
        <div class="cand-card-top">
          <div class="cand-card-name">${escapeHtml(c.template_name || '未知模板')}</div>
          <div class="cand-card-score ${scoreClass}">${pct}%</div>
        </div>
        <div class="cand-card-tags">
          ${site ? `<span class="cand-card-tag">${escapeHtml(site)}</span>` : ''}
          ${discgroup ? `<span class="cand-card-tag">${escapeHtml(discgroup)}</span>` : ''}
        </div>
        <div class="cand-card-preview">${escapeHtml(preview)}</div>
        ${prefLabel ? `<div class="cand-card-pref">📌 ${prefLabel}</div>` : ''}
      </div>`;
    }).join('');

    grid.querySelectorAll('.cand-card').forEach(card => {
      card.addEventListener('click', () => selectCandidate(parseInt(card.dataset.idx)));
    });

    const topPct = Math.round((bestScore) * 100);
    const confCol = topPct >= 80 ? '#34d399' : topPct >= 60 ? '#fbbf24' : '#fb7185';
    $('candConfBadge').textContent = topPct + '%';
    $('candConfBadge').style.color = confCol;
    show('screenCandidates');
  }

  async function selectCandidate(idx) {
    if (S.generating) return;
    const cand = S.candidates[idx];
    if (!cand) return;

    const cards = $('candGrid').querySelectorAll('.cand-card');
    cards.forEach((c, i) => c.classList.toggle('selected', i === idx));
    S.selectedCandidateIdx = idx;
    S.selectedTemplateName = cand.template_name || '';

    S.generating = true;
    const footer = document.querySelector('.candidates-footer');
    const existing = footer.querySelector('.cf-confirm');
    if (!existing) {
      const btn = document.createElement('button');
      btn.className = 'cf-btn cf-confirm';
      btn.textContent = '填充中...';
      btn.disabled = true;
      footer.appendChild(btn);
    } else {
      existing.textContent = '填充中...';
      existing.disabled = true;
    }

    try {
      await fillAndShowReview(
        cand.template_name,
        S.lastRawText,
        S.patient?.exam_type || '腹部超声'
      );
    } catch(e) {
      toast('填充失败：' + e.message, true);
      S.generating = false;
      const cb = document.querySelector('.cf-confirm');
      if (cb) { cb.textContent = '✓ 确认填充'; cb.disabled = false; }
    }
  }

  async function fillAndShowReview(templateName, rawText, examType) {
    const payload = {
      text: rawText,
      exam_type: examType,
      doctor_name: selectedDoctor(),
      template_name: templateName,
      patient_id: S.patient?.id?.toString() || '',
      patient_name: S.patient?.name || '',
      patient_gender: S.patient?.gender || S.patient?.sex || '',
      patient_age: S.patient?.age || 0,
    };
    const result = await api('POST', '/api/pad/fill', payload);
    S.generating = false;

    if (result.success || result.report) {
      S.lastReport = result;
      resetRecordUI();
      showReview(result, rawText);
    } else {
      toast('报告生成失败', true);
      show('screenDirector');
      resetRecordUI();
    }
  }

  function cancelCandidates() {
    show('screenDirector');
    resetRecordUI();
    toast('已取消，可重新录音');
  }

  function editManually() {
    show('screenDirector');
    resetRecordUI();
    toast('请重新录音或转语音报告页');
  }

  function resetRecordUI() {
    $('recordBtn').innerHTML='🎤<br>开始'; $('recordBtn').classList.remove('recording');
    $('timer').textContent='00:00'; $('wave').style.display='none';
    $('recordHint').textContent='点击开始录音'; S.chunks=[]; S.appendMode=false;
    const confirmBtn = document.querySelector('.cf-confirm');
    if (confirmBtn) confirmBtn.remove();
  }

  // ─── 实时听写模式 ───

  function toggleListening() {
    if (S.isListening) stopListening();
    else startWsRecord();
  }

  function startWsRecord() {
    if (!S.session) return toast('请先选择患者', true);
    if (!navigator.mediaDevices?.getUserMedia) return toast('浏览器不支持录音', true);
    if (!window.isSecureContext && location.hostname !== 'localhost') return toast('录音需要HTTPS', true);
    S.finalText = ''; S.interimText = ''; S.segmentCount = 0;
    clearTablet();
    navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1, sampleRate: 16000}})
      .then(stream => {
        S.stream = stream; S.isListening = true;
        updateListenUI(); toast('🎤 实时ASR连接中...', false, 'var(--blue)');
        const protocol = document.location.protocol === 'https:' ? 'wss:' : 'ws:';
        S.ws = new WebSocket(protocol + '//' + document.location.host + '/ws/asr/stream');
        S.ws.binaryType = 'arraybuffer';
        S.ws.onopen = () => {
          toast('🎤 实时ASR已连接', false, 'var(--blue)');
          const ctx = new AudioContext({sampleRate: 16000});
          const src = ctx.createMediaStreamSource(stream);
          const rec = ctx.createScriptProcessor(4096, 1, 1);
          rec.onaudioprocess = e => {
            if (S.ws && S.ws.readyState === WebSocket.OPEN) {
              const input = e.inputBuffer.getChannelData(0);
              const buf = new Int16Array(input.length);
              for (let i = 0; i < input.length; i++) {
                const s = Math.max(-1, Math.min(1, input[i]));
                buf[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
              }
              S.ws.send(buf.buffer);
            }
          };
          src.connect(rec);
          rec.connect(ctx.destination);
          S.audioCtx = ctx;
        };
        S.ws.onmessage = e => {
          const d = JSON.parse(e.data);
          if (d.type === 'partial' && d.text) {
            S.finalText += d.text;
            S.segmentCount = (S.segmentCount || 0) + 1;
            renderTabletText();
            quickPreview(S.finalText);
            // 实时获取候选模板
            tabletFetchCandidates(S.finalText);
          }
        };
        S.ws.onclose = () => { toast('ASR连接断开', true); };
        S.ws.onerror = () => { toast('ASR连接失败', true); };
      })
      .catch(e => toast('无法录音：' + e.message, true));
  }

  function stopListening() {
    S.isListening = false;
    if (S.ws) { try { S.ws.close(); } catch(_) {} S.ws = null; }
    if (S.audioCtx) { try { S.audioCtx.close(); } catch(_) {} S.audioCtx = null; }
    if (S.stream) S.stream.getTracks().forEach(t => t.stop());
    updateListenUI();
    doPreview();
  }

  function updateListenUI() {
    const btn = $('tabletListenBtn');
    if (S.isListening) { btn.textContent = '⏹ 停止'; btn.className = 'btn btn-danger'; }
    else { btn.textContent = '🎤 开始实时ASR'; btn.className = 'btn btn-blue'; }
  }

  function processCmd(t) {
    if (/清空|重来/.test(t)){clearTablet();return true;}
    if (/上一句不要|删除/.test(t)){const p=S.finalText.split(/([。！？!?])/);if(p.length<=2)S.finalText='';else{p.splice(-2);S.finalText=p.join('');}return true;}
    if (/确认报告/.test(t)){setTimeout(confirmTabletReport,300);return true;}
    return false;
  }

  function renderTabletText() {
    const el=$('recognizedText');
    let html = '';
    const segments = (S.segmentCount || 0);
    if (segments > 0) {
      for (let i = 1; i <= segments; i++) {
        html += `<span class="seg-badge ${i === segments ? 'seg-live' : 'seg-done'}">段${i}</span>`;
      }
    }
    const highlighted = highlightQuickParams(S.finalText || '');
    html += highlighted;
    if (S.isListening) html += '<span style="color:var(--muted);margin-left:8px">⏺ 录音中...</span>';
    el.innerHTML = html;
    $('finalOnly').textContent = S.finalText || '(等待语音输入)';
  }

  function highlightQuickParams(text) {
    if (!text) return '<span style="color:var(--text)">等待语音输入...</span>';
    let highlighted = text;
    highlighted = highlighted.replace(
      /(\d+(?:\.\d+)?)\s*(?:[×xX\*乘]\s*\d+(?:\.\d+)?)?\s*(mm|cm|毫米|厘米)/gi,
      '<b style="color:#f97316;font-weight:800">$&</b>'
    );
    const findKeywords = ['囊肿', '囊性', '结节', '结石', '斑块', '钙化', '占位',
      '增厚', '毛糙', '扩张', '分离', '返流', '狭窄', '积液', '积水'];
    for (const kw of findKeywords) {
      const idx = highlighted.indexOf(kw);
      if (idx >= 0) {
        const before = highlighted.slice(0, idx);
        const after = highlighted.slice(idx + kw.length);
        const wrapped = `<b style="color:#ef4444;font-weight:800">${kw}</b>`;
        if (!before.endsWith('>')) highlighted = before + wrapped + after;
      }
    }
    highlighted = highlighted.replace(
      /(大小约|厚约|长约|宽约|深约|内径约|分离约)/g,
      '<span style="color:#3b82f6;font-weight:600">$&</span>'
    );
    return `<span style="color:var(--text)">${highlighted}</span>`;
  }

  let _quickTimer = null;
  function quickPreview(text) {
    if (!text || text.length < 5) return;
    if (_quickTimer) clearTimeout(_quickTimer);
    _quickTimer = setTimeout(() => {
      _quickTimer = null;
      const nums = text.match(/\d+(?:\.\d+)?\s*(?:[×xX\*乘]\s*\d+(?:\.\d+)?)?\s*(?:mm|cm|毫米|厘米)/gi);
      const kws = [];
      const findKeywords = ['囊肿', '囊性', '结节', '结石', '斑块', '钙化', '占位',
        '增厚', '毛糙', '扩张', '分离', '返流', '狭窄', '积液'];
      for (const kw of findKeywords) {
        if (text.includes(kw)) kws.push(kw);
      }
      $('tplConf').innerHTML = nums && nums.length
        ? `<span style="color:#f97316;font-size:18px">${nums.slice(0,3).join('<br>')}</span>`
        : '<span style="color:var(--muted);font-size:14px">等待数值...</span>';
      $('previewSource').textContent = kws.length ? kws.join(', ') : '未检测到关键词';
    }, 200);
  }

  function schedulePreview() { if(S.debounceTimer)clearTimeout(S.debounceTimer);S.debounceTimer=setTimeout(()=>{S.debounceTimer=null;doPreview();},2000); }

  async function doPreview(override) {
    const t = (override?.text || S.finalText || '').trim(); if(!t) return;
    try{
      const d=await api('POST','/api/structure',{text:t,exam_type:S.patient?.exam_type||'腹部超声',doctor:selectedDoctor()});
      if(d.success){S.currentResult=d;
        $('tplName').textContent=d.template_used||'-';
        const c=Math.round((d.confidence||0)*100);const col=c>=80?'#34d399':c>=60?'#fbbf24':'#fb7185';
        $('tplConf').innerHTML=`<span style="color:${col};font-size:22px">${c}%</span>`;
        const r=d.report||{}; $('previewSee').innerHTML=renderReviewedText((r.study_see||''));
        const h=(r.study_hint||[]).filter(x=>x.checked!==false).map(x=>x.diagnosis||x).join('；');
        $('previewHint').textContent=h||'-';
        $('previewSource').textContent=t.slice(0,200);
      }
    }catch(_){}
  }

  function clearTablet() {
    S.finalText='';S.interimText='';S.currentResult=null;
    $('recognizedText').textContent='等待语音输入...';$('finalOnly').textContent='(等待语音输入)';
    $('tabletCandidates').style.display='none';
    ['tplName','tplConf','tplSite','previewSee','previewHint','previewSource'].forEach(id=>{const el=$(id);if(el)el.textContent='-';});
  }

  // ─── 实时听写候选模板 ───
  let _candTimer = null;
  async function tabletFetchCandidates(text) {
    if (!text || text.length < 8) return;
    if (_candTimer) clearTimeout(_candTimer);
    _candTimer = setTimeout(async () => {
      _candTimer = null;
      try {
        const d = await api('POST', '/api/pad/candidates', {
          text: text,
          exam_type: S.patient?.exam_type || '腹部超声',
          doctor_name: selectedDoctor(),
          site: S.patient?.exam_type || '腹部超声',
        });
        const cands = d.candidates || [];
        if (cands.length === 0) return;
        renderTabletCandidates(cands);
      } catch(_) {}
    }, 1500);
  }

  function renderTabletCandidates(cands) {
    const bar = $('tabletCandidates');
    if (!bar) return;
    bar.style.display = 'flex';
    bar.innerHTML = cands.slice(0, 6).map((c, i) => {
      const pct = Math.round((c.score || 0) * 100);
      const sel = (!S.selectedTemplateName && i === 0) || c.template_name === S.selectedTemplateName;
      return `<button class="tcand-chip${sel ? ' on' : ''}" data-tpl="${escapeHtml(c.template_name)}">
        ${escapeHtml(c.template_name.slice(0, 12))}<span class="chip-pct">${pct}%</span>
      </button>`;
    }).join('');
    bar.querySelectorAll('.tcand-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        const tpl = btn.dataset.tpl;
        S.selectedTemplateName = tpl;
        bar.querySelectorAll('.tcand-chip').forEach(b => b.classList.toggle('on', b.dataset.tpl === tpl));
        // 用选中模板重新填充预览
        if (S.finalText.length > 5) {
          previewWithTemplate(S.finalText, tpl);
        }
      });
    });
  }

  async function previewWithTemplate(text, templateName) {
    try {
      const d = await api('POST', '/api/pad/fill', {
        text: text,
        exam_type: S.patient?.exam_type || '腹部超声',
        doctor_name: selectedDoctor(),
        template_name: templateName,
      });
      if (d.success || d.report) {
        $('tplName').textContent = templateName;
        const r = d.report || {};
        const conf = Math.round((d.confidence || 0) * 100);
        const col = conf >= 80 ? '#34d399' : conf >= 60 ? '#fbbf24' : '#fb7185';
        $('tplConf').innerHTML = `<span style="color:${col};font-size:22px">${conf}%</span>`;
        $('previewSee').innerHTML = renderReviewedText(r.study_see || '');
        const h = (r.study_hint || []).filter(x => x.checked !== false).map(x => x.diagnosis || x).join('；');
        $('previewHint').textContent = h || '-';
      }
    } catch(_) {}
  }

  async function confirmTabletReport() {
    const t=(S.finalText||'').trim();if(!t)return toast('没有文本',true);
    if(!S.session)return toast('请先选择患者',true);if(S.isListening)stopListening();
    try{
      // 如果有选中的模板，用fill走精确填充
      if (S.selectedTemplateName) {
        const d = await api('POST', '/api/pad/fill', {
          text: t,
          exam_type: S.patient?.exam_type || '腹部超声',
          doctor_name: selectedDoctor(),
          template_name: S.selectedTemplateName,
          patient_id: S.patient?.id?.toString() || '',
          patient_name: S.patient?.name || '',
        });
        if (d.success) { showReview(d); } else { toast('生成失败', true); }
      } else {
        const d=await api('POST','/api/structure',{text:t,exam_type:S.patient?.exam_type||'腹部超声',doctor:selectedDoctor()});
        if(d.success){showReview(d);}else{toast('生成失败',true);}
      }
    }catch(e){toast(e.message,true);}
  }

  // ─── 报告确认弹窗 ───
  function escapeHtml(t){const e=document.createElement('span');e.textContent=String(t??'');return e.innerHTML;}

  function renderReviewedText(text) {
    if (!text) return '-';
    // 1. 未填写的占位符 → 黄色高亮
    let html = text.replace(/<i\b[^>]*>__?<\/i>/gi, '<span class="voice-unfilled">____</span>');
    html = html.replace(/__+/g, '<span class="voice-unfilled">____</span>');
    // 2. 已填充的语音值（b class="voice"）→ 橙色加粗
    html = html.replace(/<b\s+class="voice"[^>]*>([^<]+)<\/b>/gi, '<span class="voice-matched">$1</span>');
    // 3. 剩余的纯模板文本 → 浅色
    html = html.replace(/(^|>)([^<]+?)(?=<|$)/g, (m, pre, t2) => {
      if (!t2.trim()) return m;
      if (t2.includes('<') || t2.includes('span') || t2.includes('class')) return m;
      return pre + '<span class="voice-template">' + t2 + '</span>';
    });
    return html;
  }

  async function showReview(report, rawText) {
    S.lastReport = report;
    if (rawText) S.lastRawText = rawText;
    const inner=report.report?.report||report.report||report||{};
    const src=inner.sources?.A_asr||report.sources?.A_asr||rawText||'';
    const template=inner.template_used||report.template_used||'';
    const confPct=Math.round((inner.confidence||report.confidence||0)*100);
    const rd=inner.report||inner||{};
    const see=(rd.study_see||'').replace(/<i\b[^>]*>__?<\/i>/gi,'<span class="missing-var">____</span>');
    const hint=(rd.study_hint||[]).filter(h=>h.checked!==false).map(h=>h.diagnosis||h).join('；');
    const rec=inner.recommendation||rd.recommendation||'';
    const confCol=confPct>=80?'#34d399':confPct>=60?'#fbbf24':'#fb7185';
    const overlay=$('reviewOverlay');

    let candidatesHtml='', candidates=[];
    try {
      const c=await Promise.race([
        api('POST','/api/auto/process',{text:rawText||src||'肝脏'}).catch(()=>({matches:[]})),
        new Promise(r=>setTimeout(()=>r({matches:[]}),4000))
      ]);
      candidates=(c.matches||[]).slice(0,5);
      if(candidates.length>0){
        candidatesHtml=candidates.map((m,i)=>{
          const pct=Math.round(m.score*100);
          const cls=m.score>=0.8?'high':m.score>=0.6?'mid':'low';
          return `<div class="cand-row${i===0?' on':''}" data-idx="${i}"><span class="cand-score ${cls}">${pct}%</span><span class="cand-name">${escapeHtml(m.template_name)}</span></div>`;
        }).join('');
      }
    }catch(_){}

    let templateDisplay='';
    if(template) templateDisplay=template;
    else if(candidates.length>0){
      const top=candidates[0]; const topPct=Math.round(top.score*100);
      templateDisplay=`<span style="color:var(--orange)">疑似 ${escapeHtml(top.template_name)} (${topPct}%)</span>`;
    } else templateDisplay='<span style="color:var(--red)">未识别到模板</span>';

    overlay.style.display='flex';
    overlay.innerHTML=`
      <div class="review-box">
        ${report.warnings && report.warnings.length > 0 ? `
          <div style="background:rgba(239,68,68,.15);border-bottom:1px solid rgba(239,68,68,.3);padding:12px 26px;color:#fca5a5;font-size:15px;font-weight:700">
            ⚠️ 高危征象提醒
            ${report.warnings.filter(w=>w.includes('极高危')||w.includes('高危')).map(w=>`<div style="font-size:13px;font-weight:400;margin-top:2px">${escapeHtml(w)}</div>`).join('')}
          </div>` : ''}
        <div class="review-head"><h2>✅ 报告已生成 <small>${S.patient?.name||'-'}</small></h2><div style="font-size:18px;color:${confCol};font-weight:900">${confPct}%</div></div>
        <div class="review-body">
          <div class="review-item"><h3>🩺 模板 <span id="reviewTemplate">${templateDisplay}</span></h3>${candidates.length>0?`<div class="cand-list" id="candList">${candidatesHtml}</div>`:''}</div>
          <div class="review-item"><h3>📖 超声所见</h3><div class="review-text" id="reviewSee">${renderReviewedText(see||'-')}</div></div>
          <div class="review-item"><h3>💊 超声提示</h3><div class="review-text" id="reviewHint"><span class="recognized-value">${escapeHtml(hint||'-')}</span></div></div>
          <div class="review-item"><h3>🔧 建议</h3><div class="review-text" id="reviewRec"><span class="recognized-value">${escapeHtml(rec||'')}</span></div></div>
          <div class="review-item"><h3>🎤 识别原文</h3><div class="review-text" style="font-size:16px;color:var(--muted)">${escapeHtml((S.lastRawText.length > src.length ? S.lastRawText : src).slice(0, 500))}</div></div>
        </div>
        <div class="review-foot">
          <button class="btn btn-ghost" id="reviewExtraBtn">➕ 补充一句</button>
          <button class="btn btn-ghost" id="reviewEditBtn">📝 编辑</button>
          <button class="btn btn-blue" id="reviewDoneBtn">✅ 确认完成</button>
        </div>
      </div>`;

    if(candidates.length>1){
      document.querySelectorAll('.cand-row').forEach(row=>{
        row.addEventListener('click',async()=>{
          const idx=parseInt(row.dataset.idx);const m=candidates[idx];if(!m)return;
          document.querySelectorAll('.cand-row').forEach(r=>r.classList.remove('on'));row.classList.add('on');
          document.getElementById('reviewTemplate').textContent=m.template_name;
          if(m.description)document.getElementById('reviewSee').innerHTML=renderReviewedText(m.description);
        });
      });
    }

    $('reviewExtraBtn').addEventListener('click', () => {
      overlay.style.display = 'none';
      show('screenDirector');
      resetRecordUI();
      S.appendMode = true;
      $('recordHint').textContent = '补充一句后自动重新生成';
    });
    $('reviewEditBtn').addEventListener('click',()=>{
      const seeText = (rd.study_see||'').replace(/<[^>]+>/g,'');
      const hintText = hint||'';
      const recText = rec||'';
      overlay.querySelector('.review-body').innerHTML=`
        <div class="review-item"><h3>📖 超声所见</h3><textarea id="editSee" style="width:100%;min-height:120px;font-size:18px;padding:12px;border-radius:14px;background:rgba(15,23,42,.6);border:1px solid var(--line);color:#e5f0ff;font-family:var(--font)">${escapeHtml(seeText)}</textarea></div>
        <div class="review-item"><h3>💊 超声提示</h3><textarea id="editHint" style="width:100%;min-height:60px;font-size:18px;padding:12px;border-radius:14px;background:rgba(15,23,42,.6);border:1px solid var(--line);color:#e5f0ff;font-family:var(--font)">${escapeHtml(hintText)}</textarea></div>
        <div class="review-item"><h3>🔧 建议</h3><textarea id="editRec" style="width:100%;min-height:60px;font-size:18px;padding:12px;border-radius:14px;background:rgba(15,23,42,.6);border:1px solid var(--line);color:#e5f0ff;font-family:var(--font)">${escapeHtml(recText)}</textarea></div>`;
      overlay.querySelector('.review-foot').innerHTML='<button class="btn btn-ghost" id="reviewCancelEditBtn">取消</button><button class="btn btn-blue" id="reviewSaveEditBtn">💾 保存</button>';
      $('reviewCancelEditBtn').addEventListener('click', () => { overlay.style.display = 'none'; });
      $('reviewSaveEditBtn').addEventListener('click',async()=>{
        const newSee = document.getElementById('editSee')?.value || '';
        const newHint = document.getElementById('editHint')?.value || '';
        const newRec = document.getElementById('editRec')?.value || '';
        try{
          const combined = (newSee + '。提示：' + newHint + '。建议：' + newRec).replace(/[。，]{2,}/g,'。');
          const d=await api('POST','/api/structure',{text:combined,exam_type:S.patient?.exam_type||'腹部超声',doctor:selectedDoctor()});
          if(d.success){overlay.style.display='none';showReview(d);}else toast('保存失败',true);
        }catch(e){toast(e.message,true);}
      });
    });
    $('reviewDoneBtn').addEventListener('click', async () => {
      const doc = selectedDoctor();
      const tpl = document.getElementById('reviewTemplate')?.textContent || '';
      const see = document.getElementById('reviewSee')?.textContent || '';
      const hint = document.getElementById('reviewHint')?.textContent || '';
      const rec = document.getElementById('reviewRec')?.textContent || '';
      try {
        await api('POST', '/api/feedback/confirm', {
          doctor: doc || null,
          patient_id: S.patient?.id?.toString() || null,
          exam_type: S.patient?.exam_type || null,
          asr_text: S.lastRawText || null,
          template_used: tpl || null,
          study_see_final: see || null,
          study_hint_final: hint || null,
          recommendation_final: rec || null,
          confirmed: true,
        });
      } catch (e) {
        toast('确认保存异常', true);
      }
      overlay.style.display = 'none';
      resetRecordUI();
      await loadQueue();
      show('screenList');
      toast(`${S.patient?.name || ''} 确认完成`);
    });
  }

  function toast(msg,error=false,color='') {
    const el=$('toast');el.textContent=msg;
    el.style.borderColor=error?'rgba(251,113,133,.55)':(color||'rgba(56,189,248,.35)');
    el.classList.add('on');setTimeout(()=>el.classList.remove('on'),2600);
  }
})();
