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
  };

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    $('refreshBtn').addEventListener('click', loadQueue);
    $('mockBtn').addEventListener('click', seedMockPatients);
    $('backBtn').addEventListener('click', backToList);
    $('recordBtn').addEventListener('click', toggleRecord);
    tickClock(); setInterval(tickClock, 1000);
    checkSecure();
    loadQueue();
  }

  function checkSecure() {
    const ok = window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
    $('httpsWarn').style.display = ok ? 'none' : 'block';
  }

  function tickClock() {
    const d = new Date();
    $('clockTime').textContent = d.toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'});
    $('clockDate').textContent = d.toLocaleDateString('zh-CN', {year: 'numeric', month: '2-digit', day: '2-digit'});
  }

  async function api(method, path, body) {
    const opt = {method, headers: {'Content-Type': 'application/json'}};
    if (body !== undefined) opt.body = JSON.stringify(body);
    const r = await fetch(path, opt);
    if (!r.ok) {
      const e = await r.json().catch(() => ({detail: r.statusText}));
      throw new Error(e.detail || '请求失败');
    }
    return r.json();
  }

  async function seedMockPatients() {
    try {
      const d = await api('POST', '/api/workstation/mock-patients', {});
      toast(`已生成 ${d.created || 0} 个模拟患者`);
      await loadQueue();
    } catch (e) { toast(e.message, true); }
  }

  async function loadQueue() {
    $('patientGrid').textContent = '加载中...';
    try {
      const d = await api('GET', '/api/workstation/queue?status=' + encodeURIComponent('待检') + '&limit=100');
      S.patients = d.patients || [];
      renderPatients();
    } catch (e) {
      $('patientGrid').innerHTML = `<div class="error">加载失败：${escapeHtml(e.message)}</div>`;
    }
  }

  function renderPatients() {
    $('statWaiting').textContent = S.patients.length;
    $('listStatus').textContent = S.patients.length ? '等待选择' : '暂无待检';
    if (!S.patients.length) {
      $('patientGrid').innerHTML = '<div style="font-size:22px;color:var(--muted)">暂无待检患者，可点击右上角生成模拟患者。</div>';
      return;
    }
    $('patientGrid').innerHTML = S.patients.map(p => `
      <div class="patient-card" data-id="${p.id}">
        <div class="p-name">${escapeHtml(p.name || '-')}</div>
        <div class="p-meta">${escapeHtml(p.gender || p.sex || '-')} ${p.age || '-'}岁 | ${escapeHtml(p.exam_type || '-')}</div>
        <div class="p-meta">${escapeHtml(p.department || p.dept_name || '-')} | ${escapeHtml(p.exam_part || '-')}</div>
        <div class="p-tag">${escapeHtml(p.payment_status || '已缴费')}</div>
      </div>`).join('');
    document.querySelectorAll('.patient-card').forEach(card => {
      card.addEventListener('click', () => selectPatient(Number(card.dataset.id)));
    });
  }

  // ===== 报告确认弹窗 =====
  function renderReviewedText(text) {
    // 识别已填变量（非空非 __）
    const filled = (text || '').replace(/<i\b[^>]*>__?<\/i>/gi, '<span class="missing-var">____</span>');
    const result = filled
      .replace(/__+/g, '<span class="missing-var">____</span>')
      .replace(/([^\s<>])([。；；\n])/g, '$1$2') // keep natural
      .replace(/(<(?!\/?span)[^>]*>|\s*<span class="missing-var">[^<]*<\/span>\s*)/g, (m) => {
        if (m.includes('missing-var')) return m;
        return m;
      });
    // 非占位部分绿色
    return result.replace(/(^|>)([^<]+)(?=<|$)/g, (m, pre, text) => {
      if (text.trim() === '' || text.includes('span') || text.includes('class')) return m;
      return pre + text.replace(/[^<>]+/g, t => {
        if (t.includes('____')) return t;
        return `<span class="recognized-value">${t}</span>`;
      });
    });
  }

  function showReview(report) {
    const reportData = report.report || report || {};
    const see = (reportData.study_see || '').replace(/<i\b[^>]*>__?<\/i>/gi, '<span class="missing-var">____</span>');
    const hint = (reportData.study_hint || []).filter(h => h.checked !== false).map(h => h.diagnosis || h).join('；');
    const rec = reportData.recommendation || '';
    const sourceText = (report.sources?.A_asr || '') || '';
    const method = report.method || '-';
    const template = report.template_used || '-';
    const confPct = Math.round((report.confidence || 0) * 100);
    const confColor = report.confidence >= 0.8 ? '#34d399' : report.confidence >= 0.6 ? '#fbbf24' : '#fb7185';

    const overlay = document.getElementById('reviewOverlay');
    overlay.style.display = 'flex';
    overlay.innerHTML = `
      <div class="review-box">
        <div class="review-head">
          <h2>✅ 报告已生成 <small>${S.patient?.name || '-'}</small></h2>
          <div style="font-size:20px;color:${confColor};font-weight:900">${confPct}%</div>
        </div>
        <div class="review-body">
          <div class="review-item"><h3>🩺 模板 <span>${template}</span></h3></div>
          <div class="review-item"><h3>📖 超声所见</h3><div class="review-text">${renderReviewedText(see || '-')}</div></div>
          <div class="review-item"><h3>💊 超声提示</h3><div class="review-text"><span class="recognized-value">${escapeHtml(hint || '-')}</span></div></div>
          <div class="review-item"><h3>🔧 建议</h3><div class="review-text"><span class="recognized-value">${escapeHtml(rec || '-')}</span></div></div>
          <div class="review-item"><h3>🎤 识别原文</h3><div class="review-text" style="font-size:18px;color:var(--muted)">${escapeHtml(sourceText.slice(0,200))}</div></div>
        </div>
        <div class="review-foot">
          <button class="btn btn-soft" id="reviewExtraBtn">➕ 补充一句</button>
          <button class="btn btn-soft" id="reviewEditBtn">📝 手动编辑</button>
          <button class="btn btn-blue" id="reviewDoneBtn">✅ 确认完成</button>
        </div>
      </div>`;

    const extraBtn = document.getElementById('reviewExtraBtn');
    extraBtn.addEventListener('click', () => {
      // 补充：恢复录音界面并标记追加
      overlay.style.display = 'none';
      S.appendMode = true; // 标记补充模式
      show('screenRecord');
      resetRecordUI();
      $('recordHint').textContent = '补充一句话，完成后自动重新生成报告';
    });

    const editBtn = document.getElementById('reviewEditBtn');
    editBtn.addEventListener('click', () => {
      const textarea = document.createElement('textarea');
      textarea.value = (reportData.study_see || '').replace(/<[^>]+>/g, '');
      textarea.style.cssText = 'width:100%;min-height:180px;font-size:20px;padding:14px;border-radius:16px;background:rgba(15,23,42,.6);border:1px solid var(--line);color:#e5f0ff;font-family:var(--font)';
      const body = overlay.querySelector('.review-body');
      body.innerHTML = `<div class="review-item"><h3>📝 修改超声所见</h3>${textarea.outerHTML}</div>
        <div class="review-item"><h3>💊 超声提示</h3><div class="review-text"><span class="recognized-value">${escapeHtml(hint || '-')}</span></div></div>`;
      const foot = overlay.querySelector('.review-foot');
      foot.innerHTML = `<button class="btn btn-soft" id="reviewCancelEditBtn">取消</button>
        <button class="btn btn-blue" id="reviewSaveEditBtn">💾 保存修改</button>`;
      document.getElementById('reviewCancelEditBtn').addEventListener('click', () => {
        overlay.style.display = 'none';
      });
      document.getElementById('reviewSaveEditBtn').addEventListener('click', async () => {
        const newText = textarea.value;
        // 用修改后的文本直接调用structure
        try {
          const data = await api('POST', '/api/structure', {
            text: newText,
            exam_type: S.patient?.exam_type || '腹部超声',
            patient_id: String(S.patient?.id || ''),
            patient_name: S.patient?.name || '',
            patient_gender: S.patient?.gender || S.patient?.sex || '',
            patient_age: S.patient?.age || 0,
          });
          if (data.success) {
            overlay.style.display = 'none';
            showReview(data);
          } else { toast('保存失败', true); }
        } catch (e) { toast(e.message, true); }
      });
    });

    const doneBtn = document.getElementById('reviewDoneBtn');
    doneBtn.addEventListener('click', async () => {
      overlay.style.display = 'none';
      resetRecordUI();
      await loadQueue();
      show('screenList');
      toast(`${S.patient?.name || ''} 报告已确认完成`);
    });
  }

  async function selectPatient(id) {
    const p = S.patients.find(x => Number(x.id) === Number(id));
    if (!p) return;
    try {
      const d = await api('POST', '/api/workstation/sessions', {
        patient_id: p.id,
        doctor: '',
        exam_type: p.exam_type || '超声',
        exam_part: p.exam_part || '',
      });
      S.patient = d.patient;
      S.session = d.session;
      $('currentName').textContent = S.patient.name;
      $('currentMeta').textContent = `${S.patient.gender || S.patient.sex || ''} ${S.patient.age || ''}岁 | ${S.session.exam_type || S.patient.exam_type || ''} | ${S.session.exam_part || S.patient.exam_part || ''}`;
      $('currentTag').textContent = `${S.patient.department || S.patient.dept_name || ''} · ${S.patient.payment_status || '已缴费'}`;
      show('screenRecord');
    } catch (e) { toast('创建会话失败：' + e.message, true); }
  }

  function show(id) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('on'));
    $(id).classList.add('on');
  }

  function backToList() {
    if (S.recording) stopRecord(false);
    resetRecordUI();
    show('screenList');
  }

  async function toggleRecord() {
    if (S.recording) {
      await stopRecord(true);
    } else {
      await startRecord();
    }
  }

  async function startRecord() {
    if (!S.session) return toast('请先选择患者', true);
    if (!navigator.mediaDevices?.getUserMedia) return toast('浏览器不支持录音', true);
    const secure = window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
    if (!secure) return toast('录音需要HTTPS，请使用 https://47.109.151.238/director.html', true);
    try {
      S.stream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1,sampleRate:16000}});
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
      S.chunks = [];
      S.mediaRecorder = new MediaRecorder(S.stream, {mimeType});
      S.mediaRecorder.ondataavailable = e => { if (e.data && e.data.size > 0) S.chunks.push(e.data); };
      S.mediaRecorder.start(1000);
      S.recording = true;
      S.startedAt = Date.now();
      $('recordBtn').innerHTML = '⏹<br>停止生成';
      $('recordBtn').classList.add('recording');
      $('wave').style.display = 'flex';
      $('recordHint').textContent = '正在录音，完成后点停止生成报告';
      S.timerId = setInterval(updateTimer, 300);
      updateTimer();
    } catch (e) { toast('无法录音：' + e.message, true); }
  }

  async function stopRecord(autoGenerate) {
    S.recording = false;
    clearInterval(S.timerId); S.timerId = null;
    $('wave').style.display = 'none';
    $('recordBtn').classList.remove('recording');
    $('recordBtn').innerHTML = '🎤<br>开始录音';
    $('recordHint').textContent = '正在保存并生成报告...';
    if (S.mediaRecorder && S.mediaRecorder.state !== 'inactive') {
      await new Promise(resolve => {
        S.mediaRecorder.onstop = resolve;
        S.mediaRecorder.stop();
      });
    }
    if (S.stream) S.stream.getTracks().forEach(t => t.stop());
    if (autoGenerate) await processRecording();
  }

  function updateTimer() {
    const sec = Math.floor((Date.now() - S.startedAt) / 1000);
    const m = String(Math.floor(sec / 60)).padStart(2, '0');
    const s = String(sec % 60).padStart(2, '0');
    $('timer').textContent = `${m}:${s}`;
  }

  async function processRecording() {
    const blob = new Blob(S.chunks, {type:'audio/webm'});
    if (!blob || blob.size < 512) {
      toast('录音太短，请重新录制', true);
      resetRecordUI();
      return;
    }
    show('screenProcess');
    try {
      $('processTitle').textContent = '正在识别语音';
      $('processText').textContent = '保存音频并进行ASR识别...';
      const form = new FormData();
      form.append('file', blob, 'director.webm');
      form.append('doctor', '主任医生');
      const segResp = await fetch(`/api/workstation/sessions/${S.session.id}/segments`, {method:'POST', body:form});
      if (!segResp.ok) throw new Error((await segResp.json()).detail || '识别失败');
      const segData = await segResp.json();
      if (!segData.asr?.success) throw new Error((segData.asr?.warnings || ['未识别到有效语音']).join('；'));
      const asrText = segData.asr?.corrected_text || segData.asr?.text || '';

      $('processTitle').textContent = '已识别语句';
      $('processText').textContent = asrText.slice(0, 150) || '(识别为空，继续生成)';

      $('processTitle').textContent = '正在合并文本';
      $('processText').textContent = '合并当前患者有效录音段...';
      await api('POST', `/api/workstation/sessions/${S.session.id}/merge`, {});

      $('processTitle').textContent = '正在生成报告';
      $('processText').textContent = '结构化报告生成中...';
      const report = await api('POST', `/api/workstation/sessions/${S.session.id}/generate-report`, {});
      showReview(report);
    } catch (e) {
      show('screenRecord');
      resetRecordUI();
      toast(e.message, true);
    }
  }

  function showDone(text) {
    $('doneText').textContent = text + '，2秒后返回患者列表';
    show('screenDone');
    setTimeout(async () => {
      resetRecordUI();
      await loadQueue();
      show('screenList');
    }, 2000);
  }

  function resetRecordUI() {
    $('recordBtn').innerHTML = '🎤<br>开始录音';
    $('recordBtn').classList.remove('recording');
    $('timer').textContent = '00:00';
    $('wave').style.display = 'none';
    $('recordHint').textContent = '请点击开始录音';
    S.chunks = [];
    S.appendMode = false;
  }

  function toast(msg, error=false) {
    const el = $('toast');
    el.textContent = msg;
    el.style.borderColor = error ? 'rgba(251,113,133,.55)' : 'rgba(56,189,248,.35)';
    el.classList.add('on');
    setTimeout(() => el.classList.remove('on'), 2600);
  }

  function escapeHtml(t) {
    const el = document.createElement('span');
    el.textContent = String(t ?? '');
    return el.innerHTML;
  }
})();
