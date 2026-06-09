/**
 * 超声语音报告系统 - 主应用逻辑
 */

const Store = {
  state: {
    page: 'workstation',
    doctor: '',
    doctors: [],
    patients: [],
    reports: [],
    stats: {},
    templates: {},
    audioRecords: [],
    audioStorage: {},
    workstationPatients: [],
    currentPatient: null,
    currentSession: null,
    wsMediaRecorder: null,
    wsAudioChunks: [],
    wsRecording: false,
    currentResult: null,
    mediaRecorder: null,
    audioChunks: [],
    recording: false,
  },

  async init() {
    bindEvents();
    await loadInitialData();
    switchPage('workstation');
  },
};

window.addEventListener('DOMContentLoaded', () => {
  Store.init().catch(err => UI.toast('初始化失败：' + err.message, 'error'));
});

function bindEvents() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => switchPage(item.dataset.page));
  });

  const runBtn = document.getElementById('runBtn');
  if (runBtn) runBtn.addEventListener('click', runStructure);

  const runFullBtn = document.getElementById('runFullBtn');
  if (runFullBtn) runFullBtn.addEventListener('click', runFullPipeline);

  const recBtn = document.getElementById('recBtn');
  if (recBtn) recBtn.addEventListener('click', toggleRecording);

  const uploadInput = document.getElementById('uploadInput');
  if (uploadInput) uploadInput.addEventListener('change', uploadFile);

  const clearBtn = document.getElementById('clearBtn');
  if (clearBtn) clearBtn.addEventListener('click', clearReport);

  document.querySelectorAll('[data-quick]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.getElementById('voiceText').value = btn.dataset.quick;
      switchPage('voice');
      document.getElementById('voiceText').focus();
    });
  });
}

async function loadInitialData() {
  try {
    const [health, stats, doctors, patients, reports, templates, audioArchive, audioStorage] = await Promise.all([
      API.get('/api/health'),
      API.get('/api/stats'),
      API.get('/api/doctors'),
      API.get('/api/patients'),
      API.get('/api/reports'),
      API.get('/api/templates'),
      API.get('/api/audio-records?limit=50'),
      API.get('/api/audio-records/storage'),
    ]);

    Store.state.stats = stats;
    Store.state.doctors = doctors.doctors || doctors || [];
    Store.state.patients = patients.patients || [];
    Store.state.reports = reports.reports || [];
    Store.state.templates = templates || {};
    Store.state.audioRecords = audioArchive.records || [];
    Store.state.audioStorage = audioStorage || {};

    renderHeader(health);
    renderDashboard();
    renderDoctors();
    renderPatients();
    renderReports();
    renderTemplates();
    renderAudioArchive();
    await loadWorkstationQueue(false);
  } catch (err) {
    UI.toast('数据加载失败：' + err.message, 'error');
  }
}

function renderHeader(health) {
  const status = document.getElementById('sysStatus');
  if (status) {
    const secure = window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
    status.textContent = health?.status === 'ok' ? (secure ? '系统在线' : 'HTTP模式：录音受限') : '系统异常';
    status.className = 'status-badge ' + (health?.status === 'ok' ? 'online' : 'offline');
    if (!secure) status.title = '浏览器麦克风需要 HTTPS。可使用 https://47.109.151.238/ 测试（自签证书需手动信任）。';
  }

  const doctorSelect = document.getElementById('doctorSelect');
  if (doctorSelect) {
    const doctors = Store.state.doctors;
    doctorSelect.innerHTML = '<option value="">选择医生</option>' + doctors.map(d => {
      const name = d.name || d;
      return `<option value="${name}">${name}</option>`;
    }).join('');
    doctorSelect.addEventListener('change', e => { Store.state.doctor = e.target.value; });
  }
}

function switchPage(page) {
  Store.state.page = page;
  document.querySelectorAll('.nav-item').forEach(i => i.classList.toggle('on', i.dataset.page === page));
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('on', p.id === 'page-' + page));
  const title = document.querySelector(`.nav-item[data-page="${page}"] span:last-child`)?.textContent || '工作台';
  const titleEl = document.getElementById('pageTitle');
  if (titleEl) titleEl.textContent = title;
}

function renderDashboard() {
  const s = Store.state.stats || {};
  const el = document.getElementById('dashboardStats');
  if (!el) return;
  el.innerHTML = `
    <div class="stat-card"><div class="icon">📋</div><div class="value">${s.total_reports || 0}</div><div class="label">总报告</div></div>
    <div class="stat-card"><div class="icon">🕒</div><div class="value">${s.today_reports || 0}</div><div class="label">今日报告</div></div>
    <div class="stat-card"><div class="icon">✅</div><div class="value">${s.confirmed || 0}</div><div class="label">已确认</div></div>
    <div class="stat-card"><div class="icon">👥</div><div class="value">${s.total_patients || 0}</div><div class="label">患者数</div></div>
  `;
}

function renderDoctors() {
  const el = document.getElementById('doctorList');
  if (!el) return;
  const rows = Store.state.doctors.map(d => `
    <tr><td>${d.id || '-'}</td><td>${d.name || '-'}</td><td>${d.department || '超声科'}</td><td>${d.title || '-'}</td></tr>
  `).join('');
  el.innerHTML = `<table><thead><tr><th>ID</th><th>姓名</th><th>科室</th><th>职称</th></tr></thead><tbody>${rows || '<tr><td colspan="4">暂无数据</td></tr>'}</tbody></table>`;
}

function renderPatients() {
  const el = document.getElementById('patientList');
  if (!el) return;
  const rows = Store.state.patients.map(p => `
    <tr><td>${p.id}</td><td>${p.name || '-'}</td><td>${p.gender || p.sex || '-'}</td><td>${p.age || '-'}</td><td>${p.exam_type || '-'}</td><td><span class="tag tag-blue">${p.status || '待检'}</span></td></tr>
  `).join('');
  el.innerHTML = `<table><thead><tr><th>ID</th><th>姓名</th><th>性别</th><th>年龄</th><th>检查类型</th><th>状态</th></tr></thead><tbody>${rows || '<tr><td colspan="6">暂无患者</td></tr>'}</tbody></table>`;
}

function renderReports() {
  const rows = Store.state.reports.map(r => `
    <tr><td>${r.id}</td><td>${r.patient_name || '-'}</td><td>${r.template_name || r.template || '-'}</td><td>${(r.diagnosis || '').slice(0, 30)}</td><td><span class="tag ${r.status === 'confirmed' || r.status === '已确认' ? 'tag-green' : 'tag-orange'}">${r.status || '草稿'}</span></td><td>${(r.created_at || '').slice(0,16)}</td></tr>
  `).join('');
  const table = `<table><thead><tr><th>ID</th><th>患者</th><th>模板</th><th>诊断</th><th>状态</th><th>时间</th></tr></thead><tbody>${rows || '<tr><td colspan="6">暂无报告</td></tr>'}</tbody></table>`;
  const el = document.getElementById('reportList');
  if (el) el.innerHTML = table;
  const recent = document.getElementById('recentReports');
  if (recent) recent.innerHTML = table;
}

function renderTemplates() {
  const el = document.getElementById('templateList');
  if (!el) return;
  const rows = Object.entries(Store.state.templates || {}).map(([key, t]) => `
    <tr><td>${key}</td><td>${t.name || '-'}</td><td>${(t.organs || []).join('、')}</td></tr>
  `).join('');
  el.innerHTML = `<table><thead><tr><th>代码</th><th>名称</th><th>器官</th></tr></thead><tbody>${rows || '<tr><td colspan="3">暂无模板</td></tr>'}</tbody></table>`;
}

function renderAudioArchive() {
  const storageEl = document.getElementById('audioStorage');
  if (storageEl) {
    const s = Store.state.audioStorage || {};
    storageEl.innerHTML = `
      <div class="kv"><k>服务器目录</k><v style="font-family:var(--mono);font-size:12px">${s.directory || '-'}</v></div>
      <div class="kv"><k>文件数量</k><v>${s.total_files || 0}</v></div>
      <div class="kv"><k>占用空间</k><v>${s.total_mb || 0} MB</v></div>
    `;
  }
  const el = document.getElementById('audioArchive');
  if (!el) return;
  const rows = Store.state.audioRecords.map(r => {
    const asr = r.asr || {};
    const q = Number(asr.quality_score || 0);
    const qTag = q >= 0.8 ? 'tag-green' : q >= 0.6 ? 'tag-orange' : 'tag-red';
    return `<tr>
      <td>${(r.created_at || '').slice(0, 16)}</td>
      <td style="font-family:var(--mono);font-size:11px">${r.filename || '-'}</td>
      <td>${formatBytes(r.file_size || 0)}</td>
      <td>${asr.source || '-'}</td>
      <td><span class="tag ${qTag}">${Math.round(q * 100)}%</span></td>
      <td><audio controls preload="none" src="${r.play_url}" style="width:220px;height:28px"></audio></td>
      <td><button class="btn btn-outline btn-sm" onclick="showAudioDetail(${r.id})">明细</button></td>
    </tr>`;
  }).join('');
  el.innerHTML = `<table><thead><tr><th>时间</th><th>文件名</th><th>大小</th><th>ASR来源</th><th>质量</th><th>回听</th><th>操作</th></tr></thead><tbody>${rows || '<tr><td colspan="7">暂无录音档案</td></tr>'}</tbody></table>`;
}

async function loadAudioArchive() {
  const [archive, storage] = await Promise.all([
    API.get('/api/audio-records?limit=50'),
    API.get('/api/audio-records/storage'),
  ]);
  Store.state.audioRecords = archive.records || [];
  Store.state.audioStorage = storage || {};
  renderAudioArchive();
  UI.toast('语音档案已刷新', 'success');
}

async function showAudioDetail(id) {
  const d = await API.get(`/api/audio-records/${id}`);
  const audio = d.audio || {};
  const asr = (d.asr_logs || [])[0] || {};
  const reports = d.reports || [];
  const el = document.getElementById('audioDetail');
  if (!el) return;
  el.innerHTML = `
    <div class="grid-2">
      <div>
        <div class="card" style="margin-bottom:10px"><div class="card-hd">音频回听</div><div class="card-bd">
          <div class="kv"><k>原始文件</k><v>${audio.filename || '-'}</v></div>
          <audio controls src="${audio.play_url}" style="width:100%;margin:8px 0"></audio>
          ${audio.normalized_path ? `<div class="kv"><k>标准化</k><v>${audio.normalized_path.split('/').pop()}</v></div><audio controls src="${audio.normalized_play_url}" style="width:100%;margin:8px 0"></audio>` : ''}
        </div></div>
        <div class="card"><div class="card-hd">文件信息</div><div class="card-bd">
          <div class="kv"><k>路径</k><v style="font-family:var(--mono);font-size:11px">${audio.filepath || '-'}</v></div>
          <div class="kv"><k>大小</k><v>${formatBytes(audio.file_size || 0)}</v></div>
          <div class="kv"><k>状态</k><v>${audio.status || '-'}</v></div>
          <div class="kv"><k>创建时间</k><v>${audio.created_at || '-'}</v></div>
        </div></div>
      </div>
      <div>
        <div class="card" style="margin-bottom:10px"><div class="card-hd">ASR详情</div><div class="card-bd">
          <div class="kv"><k>来源</k><v>${asr.source || '-'}</v></div>
          <div class="kv"><k>质量分</k><v>${Math.round(Number(asr.quality_score || 0) * 100)}%</v></div>
          <div class="kv"><k>耗时</k><v>${asr.elapsed_seconds || 0}s</v></div>
          <label>原始ASR</label><pre style="max-height:160px;overflow:auto;background:var(--bg);padding:8px;border-radius:6px">${asr.raw_text || '-'}</pre>
          <label>纠错后</label><pre style="max-height:160px;overflow:auto;background:var(--bg);padding:8px;border-radius:6px">${asr.corrected_text || '-'}</pre>
        </div></div>
        <div class="card"><div class="card-hd">关联报告</div><div class="card-bd"><pre>${JSON.stringify(reports, null, 2)}</pre></div></div>
      </div>
    </div>`;
}

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1024 / 1024).toFixed(2) + ' MB';
}

async function seedMockPatients() {
  const res = await API.post('/api/workstation/mock-patients', {});
  UI.toast(`已生成 ${res.created || 0} 个模拟患者`, 'success');
  await loadWorkstationQueue(false);
}

async function loadWorkstationQueue(showToast = true) {
  const data = await API.get('/api/workstation/queue?status=待检&limit=100');
  Store.state.workstationPatients = data.patients || [];
  renderWorkstationQueue();
  if (showToast) UI.toast('患者队列已刷新', 'success');
}

function renderWorkstationQueue() {
  const el = document.getElementById('wsPatientQueue');
  if (!el) return;
  const rows = Store.state.workstationPatients.map(p => `
    <tr>
      <td>${p.id}</td><td>${p.name}</td><td>${p.gender || p.sex || '-'}</td><td>${p.age || '-'}</td>
      <td>${p.exam_type || '-'}</td><td>${p.exam_part || '-'}</td><td><span class="tag tag-green">${p.payment_status || '已缴费'}</span></td>
      <td><button class="btn btn-primary btn-sm" onclick="selectWorkstationPatient(${p.id})">选择</button></td>
    </tr>`).join('');
  el.innerHTML = `<table><thead><tr><th>ID</th><th>姓名</th><th>性别</th><th>年龄</th><th>检查类型</th><th>部位</th><th>缴费</th><th>操作</th></tr></thead><tbody>${rows || '<tr><td colspan="8">暂无待检患者，请点击生成20个模拟患者</td></tr>'}</tbody></table>`;
}

async function selectWorkstationPatient(patientId) {
  const patient = Store.state.workstationPatients.find(p => Number(p.id) === Number(patientId));
  const doctor = Store.state.doctor || document.getElementById('doctorSelect')?.value || '';
  const data = await API.post('/api/workstation/sessions', {
    patient_id: patientId,
    doctor,
    exam_type: patient?.exam_type || '',
    exam_part: patient?.exam_part || '',
  });
  Store.state.currentPatient = data.patient;
  Store.state.currentSession = data.session;
  await refreshCurrentSession();
  UI.toast(`已选择患者：${data.patient.name}`, 'success');
}

async function refreshCurrentSession() {
  const session = Store.state.currentSession;
  if (!session) return;
  const data = await API.get(`/api/workstation/sessions/${session.id}`);
  Store.state.currentSession = data.session;
  Store.state.currentPatient = data.patient;
  renderWorkstationSession(data);
}

function renderWorkstationSession(data) {
  const patient = data.patient || Store.state.currentPatient || {};
  const session = data.session || Store.state.currentSession || {};
  const segments = data.segments || [];
  const panel = document.getElementById('wsSessionPanel');
  if (panel) {
    panel.innerHTML = `
      <div class="kv"><k>患者</k><v>${patient.name || '-'} ${patient.gender || patient.sex || ''} ${patient.age || ''}岁</v></div>
      <div class="kv"><k>检查</k><v>${session.exam_type || patient.exam_type || '-'} / ${session.exam_part || patient.exam_part || '-'}</v></div>
      <div class="kv"><k>会话号</k><v style="font-family:var(--mono)">${session.session_no || '-'}</v></div>
      <div class="kv"><k>状态</k><v><span class="tag tag-blue">${session.status || '-'}</span></v></div>
      <div class="kv"><k>段数</k><v>${segments.length}</v></div>`;
  }
  const status = document.getElementById('wsRecordStatus');
  if (status) status.textContent = patient.name ? `当前：${patient.name}` : '未选择患者';
  renderWsSegments(segments);
  const merged = document.getElementById('wsMergedText');
  if (merged) merged.value = session.merged_text || '';
}

function renderWsSegments(segments) {
  const el = document.getElementById('wsSegments');
  if (!el) return;
  const rows = segments.map(s => {
    const q = Number(s.quality_score || 0);
    const tag = q >= 0.8 ? 'tag-green' : q >= 0.6 ? 'tag-orange' : 'tag-red';
    const playUrl = `/api/workstation/segments/${s.id}/play?kind=original`;
    const dur = s.duration_seconds ? formatDuration(s.duration_seconds) : '';
    return `<tr>
      <td>${s.segment_no}</td><td>${(s.created_at || '').slice(0,16)}</td><td>${dur || '<span class="text-muted">--</span>'}</td><td>${s.asr_source || '-'}</td>
      <td><span class="tag ${tag}">${Math.round(q*100)}%</span></td>
      <td>${s.is_valid ? '<span class="tag tag-green">有效</span>' : '<span class="tag tag-red">无效</span>'}</td>
      <td><audio controls preload="none" src="${playUrl}" style="width:220px;height:28px"></audio></td>
      <td style="max-width:280px;color:var(--text-secondary);font-size:12px">${(s.corrected_text || s.raw_text || '').slice(0,80)}</td>
    </tr>`;
  }).join('');
  el.innerHTML = `<table><thead><tr><th>段</th><th>时间</th><th>时长</th><th>ASR</th><th>质量</th><th>状态</th><th>回听</th><th>文本预览</th></tr></thead><tbody>${rows || '<tr><td colspan="8">暂无录音段</td></tr>'}</tbody></table>`;
}

function formatDuration(sec) {
  if (!sec) return '';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return m ? `${m}分${s}秒` : `${s}秒`;
}

async function toggleWsRecording() {
  if (!Store.state.currentSession) return UI.toast('请先选择患者', 'error');
  if (Store.state.wsRecording) return stopWsRecording();
  if (!navigator.mediaDevices?.getUserMedia) return UI.toast('浏览器不支持录音', 'error');
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1, sampleRate: 16000 } });
    Store.state.wsAudioChunks = [];
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
    Store.state.wsMediaRecorder = new MediaRecorder(stream, { mimeType });
    Store.state.wsMediaRecorder.ondataavailable = e => { if (e.data && e.data.size > 0) Store.state.wsAudioChunks.push(e.data); };
    Store.state.wsMediaRecorder.onstop = async () => {
      const blob = new Blob(Store.state.wsAudioChunks, { type: mimeType });
      await uploadWsBlob(blob, 'webm');
      stream.getTracks().forEach(t => t.stop());
    };
    Store.state.wsMediaRecorder.start(1000);
    Store.state.wsRecording = true;
    document.getElementById('wsRecordBtn').textContent = '⏹ 停止并保存';
    document.getElementById('wsRecordStatus').textContent = '录音中...';
  } catch (err) {
    UI.toast('无法录音：' + err.message, 'error');
  }
}

function stopWsRecording() {
  Store.state.wsRecording = false;
  Store.state.wsMediaRecorder?.stop();
  document.getElementById('wsRecordBtn').textContent = '🎤 开始录音';
  document.getElementById('wsRecordStatus').textContent = '上传识别中...';
}

async function uploadWsSegment(input) {
  if (!Store.state.currentSession) return UI.toast('请先选择患者', 'error');
  const file = input.files[0];
  if (!file) return;
  await uploadWsBlob(file, file.name.split('.').pop() || 'webm');
  input.value = '';
}

async function uploadWsBlob(blob, format) {
  if (!blob || blob.size < 512) return UI.toast('录音太短或为空', 'error');
  const form = new FormData();
  form.append('file', blob, `segment.${format || 'webm'}`);
  form.append('doctor', Store.state.doctor || '');
  const resp = await fetch(`/api/workstation/sessions/${Store.state.currentSession.id}/segments`, { method: 'POST', body: form });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    UI.toast(err.detail || '上传分段失败', 'error');
    return;
  }
  const data = await resp.json();
  UI.toast(data.asr?.success ? '分段识别完成' : '分段已保存，但识别无效', data.asr?.success ? 'success' : 'error');
  await refreshCurrentSession();
}

async function mergeCurrentSession() {
  if (!Store.state.currentSession) return UI.toast('请先选择患者', 'error');
  const data = await API.post(`/api/workstation/sessions/${Store.state.currentSession.id}/merge`, {});
  document.getElementById('wsMergedText').value = data.merged_text || '';
  Store.state.currentSession = data.session;
  UI.toast('已合并有效录音文本', 'success');
}

async function generateCurrentReport() {
  if (!Store.state.currentSession) return UI.toast('请先选择患者', 'error');
  const data = await API.post(`/api/workstation/sessions/${Store.state.currentSession.id}/generate-report`, {});
  document.getElementById('wsMergedText').value = data.merged_text || '';
  UI.renderResult(data.report);
  document.getElementById('wsReportResult').innerHTML = `<pre>${JSON.stringify(data.report, null, 2)}</pre>`;
  UI.toast('报告已生成', 'success');
  await refreshCurrentSession();
}

async function runStructure() {
  const text = document.getElementById('voiceText').value.trim();
  const examType = document.getElementById('examType').value;
  if (!text) return UI.toast('请输入语音文本', 'error');
  setStatus('处理中...');
  try {
    const result = await API.post('/api/structure', { text, exam_type: examType });
    Store.state.currentResult = result;
    UI.renderResult(result);
    document.getElementById('rawJson').textContent = JSON.stringify(result, null, 2);
    setStatus('完成');
    UI.toast('结构化完成', 'success');
  } catch (err) {
    setStatus('失败');
    UI.toast(err.message, 'error');
  }
}

async function runFullPipeline() {
  const text = document.getElementById('voiceText').value.trim();
  const examType = document.getElementById('examType').value;
  if (!text) return UI.toast('请输入语音文本', 'error');
  setStatus('全流程分析中...');
  try {
    const [result, health, stats, cheatsheet] = await Promise.all([
      API.post('/api/structure', { text, exam_type: examType }),
      API.get('/api/health'),
      API.get('/api/stats'),
      API.get('/api/auto/cheatsheet'),
    ]);
    Store.state.currentResult = result;
    UI.renderResult(result);
    UI.renderTimeline(result, text);
    UI.renderKB(health);
    UI.renderDB(stats);
    document.getElementById('rawJson').textContent = JSON.stringify(result, null, 2);
    setStatus('完成');
    UI.toast(`全流程完成，加载 ${cheatsheet.length || 0} 条提示卡`, 'success');
  } catch (err) {
    setStatus('失败');
    UI.toast('全流程失败：' + err.message, 'error');
  }
}

function setStatus(text) {
  const el = document.getElementById('rStatus');
  if (el) el.textContent = text;
}

function clearReport() {
  document.getElementById('voiceText').value = '';
  ['rSee','rHints','rRec','rMeta'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<span style="color:var(--text-muted)">等待输入...</span>';
  });
  document.getElementById('rawJson').textContent = '{}';
  const tl = document.getElementById('tlSteps');
  if (tl) tl.innerHTML = '运行管线后显示...';
  setStatus('就绪');
}

async function toggleRecording() {
  if (Store.state.recording) return stopRecording();
  if (!navigator.mediaDevices?.getUserMedia) return UI.toast('浏览器不支持录音', 'error');
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
        sampleRate: 16000,
      }
    });
    Store.state.audioChunks = [];
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
    Store.state.mediaRecorder = new MediaRecorder(stream, { mimeType });
    Store.state.mediaRecorder.ondataavailable = e => {
      if (e.data && e.data.size > 0) Store.state.audioChunks.push(e.data);
    };
    Store.state.mediaRecorder.onstop = async () => {
      const blob = new Blob(Store.state.audioChunks, { type: mimeType });
      await handleAudioBlob(blob, 'webm');
      stream.getTracks().forEach(t => t.stop());
    };
    Store.state.mediaRecorder.start(1000);
    Store.state.recording = true;
    document.getElementById('recBtn').textContent = '⏹ 停止录音';
    document.getElementById('recIndicator').textContent = '录音中...';
    UI.toast('开始录音', 'info');
  } catch (err) {
    UI.toast('无法访问麦克风：' + err.message, 'error');
  }
}

function stopRecording() {
  Store.state.recording = false;
  Store.state.mediaRecorder?.stop();
  document.getElementById('recBtn').textContent = '🎤 录音';
  document.getElementById('recIndicator').textContent = '识别中...';
}

async function uploadFile(e) {
  const file = e.target.files[0];
  if (!file) return;
  await handleAudioBlob(file, file.name.split('.').pop() || 'webm');
  e.target.value = '';
}

async function handleAudioBlob(blob, format) {
  try {
    if (!blob || blob.size < 512) {
      UI.toast('录音太短或为空，请重新录制', 'error');
      return;
    }
    document.getElementById('recIndicator').textContent = 'ASR识别中...';
    const data = await API.uploadAudio(blob, format, {
      exam_type: document.getElementById('examType')?.value || '腹部超声',
      run_structure: false,
    });
    const text = data.corrected_text || data.text || data.raw_text || '';
    if (text) {
      document.getElementById('voiceText').value = text;
      const quality = typeof data.quality_score === 'number' ? `，质量${Math.round(data.quality_score * 100)}%` : '';
      const source = data.source ? `（${data.source}${data.fallback_used ? '兜底' : ''}）` : '';
      UI.toast(`识别完成${source}${quality}`, 'success');
      await runFullPipeline();
    } else {
      const warning = (data.warnings || []).join('；');
      UI.toast('未识别到文字' + (warning ? '：' + warning : '，可手动输入'), 'error');
    }
  } catch (err) {
    UI.toast('语音识别失败：' + err.message, 'error');
  } finally {
    document.getElementById('recIndicator').textContent = '就绪';
  }
}

async function refreshAll() {
  await loadInitialData();
  UI.toast('数据已刷新', 'success');
}
