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

  // 切换到时自动加载日志数据
  if (page === 'accesslog') {
    loadAccessLogs();
    loadAccessLogStats();
  }
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

function _checkMicPermission() {
  if (!navigator.mediaDevices?.getUserMedia) {
    UI.toast('当前浏览器不支持麦克风 API，请使用 Chrome/Edge 最新版', 'error');
    return false;
  }
  if (!window.isSecureContext && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
    UI.toast('🔒 录音需要 HTTPS 安全连接。请使用 https://47.109.151.238/ 访问', 'error');
    return false;
  }
  return true;
}

async function toggleWsRecording() {
  if (!Store.state.currentSession) return UI.toast('请先选择患者', 'error');
  if (Store.state.wsRecording) return stopWsRecording();
  if (!_checkMicPermission()) return;
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
  // 先取候选模板
  const ok = await _fetchAndShowCandidates(text, examType);
  if (!ok) {
    // 候选失败或无 → 直接结构化
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
  if (!_checkMicPermission()) return;
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
      // 候选模板选择（异步弹出）
      await _fetchAndShowCandidates(text, document.getElementById('examType')?.value || '腹部超声');
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

/* ─── 访问日志 ─── */

async function loadAccessLogs() {
  const el = document.getElementById('accessLogTable');
  if (!el) return;
  const methodFilter = document.getElementById('alFilterMethod')?.value || '';
  const q = document.getElementById('alFilterSearch')?.value || '';
  try {
    let url = '/api/access-log?limit=500';
    if (q) url += '&q=' + encodeURIComponent(q);
    if (methodFilter) url += '&method_filter=' + encodeURIComponent(methodFilter);
    const data = await API.get(url);
    renderAccessLogs(data);
  } catch (err) {
    UI.toast('加载访问日志失败：' + err.message, 'error');
  }
}

function renderAccessLogs(data) {
  const el = document.getElementById('accessLogTable');
  if (!el) return;
  const logs = data.logs || [];
  const rows = logs.map(log => {
    const m = log.route_method || log.method || 'GET';
    const methCls = m === 'converted_fill' ? 'tag-green' : m === 'template_fill' ? 'tag-orange' : m === 'llm_free' ? 'tag-red' : 'tag-blue';
    return `<tr>
      <td style="white-space:nowrap;font-family:var(--mono);font-size:11px">${(log.created_at || '').slice(0,19)}</td>
      <td style="font-family:var(--mono);font-size:11px;color:var(--text-secondary)">${log.ip || '-'}</td>
      <td style="font-size:11px;color:var(--text-muted)">${log.province || ''}${log.city ? ' ' + log.city : ''}</td>
      <td style="font-size:11px;color:var(--text-secondary);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(log.path || '')}</td>
      <td><span class="tag ${methCls}" style="font-size:10px">${escapeHtml(m)}</span></td>
      <td style="font-size:11px;color:var(--text-secondary);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(log.template_used || '-')}</td>
      <td style="font-family:var(--mono);font-size:11px">${log.elapsed_ms || '-'}</td>
      <td style="font-family:var(--mono);font-size:11px">${log.confidence ? Math.round(log.confidence*100)+'%' : '-'}</td>
      <td><span class="tag ${(log.status_code||200)>=400?'tag-red':(log.status_code||200)>=300?'tag-orange':'tag-blue'}">${log.status_code || 200}</span></td>
    </tr>`;
  }).join('');
  el.innerHTML = `<div style="padding:2px 0 6px;font-size:12px;color:var(--text-muted)">共 ${data.total || logs.length} 条记录（显示 ${logs.length} 条）</div>
    <table><thead><tr><th>时间</th><th>IP</th><th>地区</th><th>路径</th><th>方法</th><th>模板</th><th>耗时ms</th><th>置信度</th><th>状态</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:30px">暂无日志</td></tr>'}</tbody></table>`;
}

async function loadAccessLogStats() {
  try {
    const data = await API.get('/api/access-log/stats');
    renderAccessLogStats(data);
  } catch (err) {
    console.warn('加载访问日志统计失败:', err);
  }
}

function renderAccessLogStats(data) {
  const el = document.getElementById('accessLogStats');
  if (!el) return;
  el.innerHTML = `
    <div class="stat-card-modern"><div class="icon">👁</div><div class="val">${data.today || 0}</div><div class="lbl">今日访问</div></div>
    <div class="stat-card-modern"><div class="icon">📈</div><div class="val">${data.total || 0}</div><div class="lbl">总记录</div></div>
    <div class="stat-card-modern"><div class="icon">⚠</div><div class="val" style="color:${(data.errors_today||0)>0?'#ef4444':'#16a34a'}">${data.errors_today || 0}</div><div class="lbl">今日异常</div></div>
  `;

  // 地区分布
  const regionEl = document.getElementById('accessLogRegion');
  if (regionEl && data.region_distribution) {
    const maxCnt = Math.max(...data.region_distribution.map(r => r.count), 1);
    regionEl.innerHTML = data.region_distribution.length
      ? data.region_distribution.map(r => {
          const pct = (r.count / maxCnt * 100).toFixed(0);
          const label = [r.province, r.city].filter(Boolean).join(' ');
          return `<div style="display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px"><span style="width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(label)}</span><div style="flex:1;height:14px;background:#e2e8f0;border-radius:4px;overflow:hidden"><div style="height:100%;width:${pct}%;background:linear-gradient(90deg,#3b82f6,#1d4ed8);border-radius:4px;transition:width .3s"></div></div><span style="width:36px;text-align:right;color:var(--text-muted);font-family:var(--mono);font-size:11px">${r.count}</span></div>`;
        }).join('')
      : '<span style="color:var(--text-muted);font-size:12px">暂无地区数据（需配置 GeoIP 数据库）</span>';
  }

  // 方法分布
  const methodEl = document.getElementById('accessLogMethod');
  if (methodEl && data.method_distribution) {
    const all = data.method_distribution.reduce((s, m) => s + m.count, 0) || 1;
    methodEl.innerHTML = data.method_distribution.length
      ? data.method_distribution.map(m => {
          const pct = (m.count / all * 100).toFixed(0);
          const colors = {converted_fill:'#16a34a', template_fill:'#d97706', llm_free:'#ef4444', llm_multi:'#8b5cf6'};
          const color = colors[m.method] || '#64748b';
          return `<div style="display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px"><span style="width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(m.method)}</span><div style="flex:1;height:14px;background:#e2e8f0;border-radius:4px;overflow:hidden"><div style="height:100%;width:${pct}%;background:${color};border-radius:4px;transition:width .3s"></div></div><span style="width:48px;text-align:right;color:var(--text-muted);font-family:var(--mono);font-size:11px">${m.count} (${pct}%)</span></div>`;
        }).join('')
      : '<span style="color:var(--text-muted);font-size:12px">暂无方法数据</span>';
  }
}

/* ─── 候选模板选择（主页面模态框） ─── */

function escapeHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function _fetchAndShowCandidates(text, examType) {
  let cands;
  try {
    const resp = await API.post('/api/pad/candidates', {
      text: text,
      exam_type: examType,
      doctor_name: Store.state.doctor || '',
      site: examType,
    });
    cands = resp.candidates || [];
  } catch (e) {
    console.warn('候选获取失败，直接走原流程:', e);
    return false;
  }

  if (!cands || cands.length <= 1) return false; // 无候选或仅1个 → 不弹窗，直接自动填充

  // 有多个候选 → 弹窗让医生选
  _showCandidatesModal(text, examType, cands);
  return true;
}

function _showCandidatesModal(text, examType, candidates) {
  const html = `
    <div style="margin-bottom:14px;font-size:12px;color:#64748b;word-break:break-all">
      🎤 <span style="color:#0f172a">${escapeHtml(text.slice(0, 180))}</span>
    </div>
    <div style="display:grid;grid-template-columns:1fr;gap:8px;" id="candModalGrid">
      ${candidates.map((c, i) => _candCardHtml(c, i)).join('')}
    </div>`;

  const modal = UI.modal('🎯 选择匹配模板', html, `
    <button class="btn btn-outline btn-sm" onclick="this.closest('.modal-overlay').remove(); _fallbackStructure()">跳过 → 直接生成</button>
  `);

  modal.querySelectorAll('.cand-card').forEach(card => {
    card.addEventListener('click', () => {
      const idx = parseInt(card.dataset.idx);
      const cand = candidates[idx];
      if (!cand) return;
      modal.querySelector('.modal-overlay, .modal')?.closest('.modal-overlay')?.remove();
      _fillWithCandidate(text, examType, cand);
    });
  });
}

function _candCardHtml(c, i) {
  const pct = Math.round((c.score || 0) * 100);
  const scoreCls = pct >= 80 ? 'cand-green' : pct >= 60 ? 'cand-yellow' : 'cand-red';
  const preview = (c.description || '').replace(/<[^>]+>/g, '').slice(0, 80);
  return `<div class="cand-card" data-idx="${i}" style="background:#f8fafc;border:1.5px solid #e2e8f0;border-radius:10px;padding:12px 14px;cursor:pointer;transition:.12s">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <div style="font-weight:600;font-size:13px;color:#0f172a">${escapeHtml(c.template_name || '未知模板')}</div>
      <div style="font-size:15px;font-weight:700;color:${pct>=80?'#16a34a':pct>=60?'#d97706':'#ef4444'}">${pct}%</div>
    </div>
    ${preview ? `<div style="font-size:11px;color:#475569;margin-top:4px">${escapeHtml(preview)}</div>` : ''}
    ${c.preference_boost > 0 ? `<div style="font-size:11px;color:#f59e0b;margin-top:4px">📌 常用 +${Math.round(c.preference_boost * 100)}%</div>` : ''}
  </div>`;
}

let _pendingFallbackText = '';
let _pendingFallbackExam = '';

async function _fillWithCandidate(text, examType, cand) {
  setStatus('填充中...');
  try {
    const result = await API.post('/api/pad/fill', {
      text: text,
      exam_type: examType,
      doctor_name: Store.state.doctor || '',
      template_name: cand.template_name || cand.name || '',
    });
    Store.state.currentResult = result;
    UI.renderResult(result);
    document.getElementById('rawJson').textContent = JSON.stringify(result, null, 2);
    setStatus('完成');
    UI.toast(`已用模板「${cand.template_name || cand.name || ''}」填充`, 'success');
  } catch (err) {
    setStatus('失败');
    UI.toast('填充失败：' + err.message + '，已降级直接结构化', 'error');
    _fallbackStructure();
  }
}

function _fallbackStructure() {
  const text = document.getElementById('voiceText').value.trim();
  const examType = document.getElementById('examType').value;
  if (text) runStructure();
}
