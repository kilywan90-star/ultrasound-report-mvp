/**
 * 超声平板 - 合并版 (主任极简 + 实时听写)
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
  };

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    bindEvents();
    tickClock(); setInterval(tickClock, 1000);
    checkSecure();
    loadQueue();
  }

  function bindEvents() {
    $('refreshBtn').addEventListener('click', loadQueue);
    $('mockBtn').addEventListener('click', seedMockPatients);
    $('backBtn').addEventListener('click', backToList);
    $('recordBtn').addEventListener('click', toggleRecord);
    $('modeDirector').addEventListener('click', () => switchMode('director'));
    $('modeTablet').addEventListener('click', () => switchMode('tablet'));
    $('tabletListenBtn').addEventListener('click', toggleListening);
    $('tabletClearBtn').addEventListener('click', clearTablet);
    $('tabletDoneBtn').addEventListener('click', confirmTabletReport);
  }

  function switchMode(mode) {
    // 停止当前模式的所有活动
    if (S.recording) { stopRecord(false); resetRecordUI(); }
    if (S.isListening) { stopListening(); }
    S.mode = mode;
    $('modeDirector').classList.toggle('on', mode === 'director');
    $('modeTablet').classList.toggle('on', mode === 'tablet');
    if (mode === 'director') {
      $('mainTitle').textContent = '超声平板';
      $('modeHint').textContent = '主任极简 · 选病人 录语音 自动生成';
      $('stepGuide').innerHTML = '1 选患者<br>2 开始录音<br>3 停止生成';
    } else {
      $('mainTitle').textContent = '超声平板';
      $('modeHint').textContent = '实时听写 · 边说边看 模板实时识别';
      $('stepGuide').innerHTML = '1 选患者<br>2 开始监听<br>3 确认报告';
    }
    // 切换后回到患者列表
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

  async function loadQueue() {
    $('patientGrid').textContent = '加载中...';
    try {
      const d = await api('GET','/api/workstation/queue?status='+encodeURIComponent('待检')+'&limit=100');
      S.patients = d.patients || [];
      renderPatients();
    } catch(e) { $('patientGrid').innerHTML = `<div class="error">加载失败：${escapeHtml(e.message)}</div>`; }
  }

  function renderPatients() {
    $('statWaiting').textContent = S.patients.length;
    $('listStatus').textContent = S.patients.length ? '等待选择' : '暂无待检';
    if (!S.patients.length) { $('patientGrid').innerHTML = '<div style="font-size:20px;color:var(--muted)">暂无待检患者</div>'; return; }
    $('patientGrid').innerHTML = S.patients.map(p =>
      `<div class="patient-card" data-id="${p.id}"><div class="p-name">${escapeHtml(p.name)}</div><div class="p-meta">${escapeHtml(p.gender||p.sex||'-')} ${p.age||'-'}岁 | ${escapeHtml(p.exam_type||'-')}</div><div class="p-meta">${escapeHtml(p.department||p.dept_name||'-')}</div><div class="p-tag">${escapeHtml(p.payment_status||'已缴费')}</div></div>`
    ).join('');
    document.querySelectorAll('.patient-card').forEach(c => c.addEventListener('click', ()=>selectPatient(Number(c.dataset.id))));
  }

  async function selectPatient(id) {
    const p = S.patients.find(x => Number(x.id)===Number(id)); if (!p) return;
    try {
      const d = await api('POST','/api/workstation/sessions',{patient_id:p.id,doctor:'',exam_type:p.exam_type||'超声',exam_part:p.exam_part||''});
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
  function backToList() { if(S.recording) stopRecord(false); resetRecordUI(); if(S.isListening) stopListening(); show('screenList'); }

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

  async function processRecording() {
    const blob = new Blob(S.chunks,{type:'audio/webm'});
    if (!blob||blob.size<512) { toast('录音太短',true); resetRecordUI(); show('screenDirector'); return; }
    show('screenProcess');
    try {
      $('processTitle').textContent='识别中';
      const form=new FormData(); form.append('file',blob,'pad.webm'); form.append('doctor','主任医生');
      const segResp = await fetch(`/api/workstation/sessions/${S.session.id}/segments`,{method:'POST',body:form});
      if (!segResp.ok) throw new Error((await segResp.json()).detail||'识别失败');
      const segData = await segResp.json();
      if (!segData.asr?.success) throw new Error((segData.asr?.warnings||['未识别到有效语音']).join('；'));
      $('processText').textContent=(segData.asr?.corrected_text||'').slice(0,150);
      $('processTitle').textContent='合并中';
      await api('POST',`/api/workstation/sessions/${S.session.id}/merge`,{});
      $('processTitle').textContent='生成报告';
      const report = await api('POST',`/api/workstation/sessions/${S.session.id}/generate-report`,{});
      const rawText = segData.asr?.corrected_text || segData.asr?.raw_text || '';
      showReview(report, rawText);
    } catch(e) { show('screenDirector'); resetRecordUI(); toast(e.message,true); }
  }

  function resetRecordUI() {
    $('recordBtn').innerHTML='🎤<br>开始'; $('recordBtn').classList.remove('recording');
    $('timer').textContent='00:00'; $('wave').style.display='none';
    $('recordHint').textContent='点击开始录音'; S.chunks=[]; S.appendMode=false;
  }

  function toggleListening() { if(S.isListening) stopListening(); else startWsRecord(); }

  function startWsRecord() {
    if (!S.session) return toast('请先选择患者',true);
    if (!navigator.mediaDevices?.getUserMedia) return toast('浏览器不支持录音',true);
    if (!window.isSecureContext && location.hostname !== 'localhost') return toast('录音需要HTTPS',true);
    S.finalText=''; S.interimText=''; S.segmentCount=0;
    clearTablet();
    navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1,sampleRate:16000}}).then(stream=>{
      S.stream=stream; S.isListening=true;
      updateListenUI(); toast('🎤 实时ASR连接中...',false,'var(--blue)');
      S.ws=new WebSocket((document.location.protocol==='https:'?'wss:':'ws:')+'//'+document.location.host+'/ws/asr/stream');
      S.ws.binaryType='arraybuffer';
      S.ws.onopen=()=>{
        toast('🎤 实时ASR已连接',false,'var(--blue)');
        const ctx=new AudioContext({sampleRate:16000});
        const src=ctx.createMediaStreamSource(stream);
        const rec=ctx.createScriptProcessor(4096,1,1);
        rec.onaudioprocess=e=>{
          if(S.ws&&S.ws.readyState===WebSocket.OPEN){
            const input=e.inputBuffer.getChannelData(0);
            const buf=new Int16Array(input.length);
            for(let i=0;i<input.length;i++){const s=Math.max(-1,Math.min(1,input[i]));buf[i]=s<0?s*0x8000:s*0x7FFF;}
            S.ws.send(buf.buffer);
          }
        };
        src.connect(rec);
        rec.connect(ctx.destination);
        S.audioCtx=ctx;
      };
      S.ws.onmessage=e=>{
        const d=JSON.parse(e.data);
        if(d.type==='partial'&&d.text){
          S.finalText+=d.text;
          S.segmentCount=(S.segmentCount||0)+1;
          renderTabletText();
          doPreview({text:S.finalText,exam_type:S.patient?.exam_type||'腹部超声'});
        }
      };
      S.ws.onclose=()=>{ toast('ASR连接断开',true); };
      S.ws.onerror=()=>{ toast('ASR连接失败',true); };
    }).catch(e=>toast('无法录音：'+e.message,true));
  }

  function stopListening() {
    S.isListening=false;
    if(S.ws){try{S.ws.close()}catch(_){}S.ws=null;}
    if(S.audioCtx){try{S.audioCtx.close()}catch(_){}S.audioCtx=null;}
    if(S.stream)S.stream.getTracks().forEach(t=>t.stop());
    updateListenUI();
    updateListenUI(); doPreview();
  }

  function updateListenUI() {
    const btn=$('tabletListenBtn');
    if(S.isListening){btn.textContent='⏹ 停止';btn.className='btn btn-danger';}else{btn.textContent='🎤 开始实时ASR';btn.className='btn btn-blue';}
  }

  function processCmd(t) {
    if(/清空|重来/.test(t)){clearTablet();return true;}
    if(/上一句不要|删除/.test(t)){const p=S.finalText.split(/([。！？!?])/);if(p.length<=2)S.finalText='';else{p.splice(-2);S.finalText=p.join('');}return true;}
    if(/确认报告/.test(t)){setTimeout(confirmTabletReport,300);return true;}
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
    html += `<span style="color:var(--text)">${escapeHtml(S.finalText)}</span>`;
    if (S.isListening) html += '<span style="color:var(--muted);margin-left:8px">⏺ 录音中...</span>';
    el.innerHTML = html;
    $('finalOnly').textContent = S.finalText || '(等待语音输入)';
  }

  function schedulePreview() { if(S.debounceTimer)clearTimeout(S.debounceTimer);S.debounceTimer=setTimeout(()=>{S.debounceTimer=null;doPreview();},2000); }

  async function doPreview(override) {
    const t = (override?.text || S.finalText || '').trim(); if(!t) return;
    try{
      const d=await api('POST','/api/structure',{text:t,exam_type:S.patient?.exam_type||'腹部超声'});
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
    ['tplName','tplConf','tplSite','previewSee','previewHint','previewSource'].forEach(id=>{const el=$(id);if(el)el.textContent='-';});
  }

  async function confirmTabletReport() {
    const t=(S.finalText||'').trim();if(!t)return toast('没有文本',true);
    if(!S.session)return toast('请先选择患者',true);if(S.isListening)stopListening();
    try{
      const d=await api('POST','/api/structure',{text:t,exam_type:S.patient?.exam_type||'腹部超声'});
      if(d.success){showReview(d);}else{toast('生成失败',true);}
    }catch(e){toast(e.message,true);}
  }

  // ── 报告确认弹窗（含候选模板切换）──
  function escapeHtml(t){const e=document.createElement('span');e.textContent=String(t??'');return e.innerHTML;}
  function renderReviewedText(text) {
    const t=(text||'').replace(/<i\b[^>]*>__?<\/i>/gi,'<span class="missing-var">____</span>').replace(/__+/g,'<span class="missing-var">____</span>');
    return t.replace(/(^|>)([^<]+)(?=<|$)/g,(m,pre,t)=>{if(!t.trim()||t.includes('span')||t.includes('class'))return m;return pre+t.replace(/[^<>]+/g,x=>x.includes('____')?x:`<span class="recognized-value">${x}</span>`);});
  }

  async function showReview(report, rawText) {
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

    // 获取候选模板
    let candidatesHtml='', candidates=[];
    try {
      const c=await Promise.race([
        api('POST','/api/auto/process',{text:rawText||src||'肝脏'}).catch(()=>({matches:[]})),
        new Promise(r=>setTimeout(()=>r({matches:[]}),4000))
      ]);
      candidates=(c.matches||[]).slice(0,5);
      if(candidates.length>0){
        const text=rawText||src||'';
        candidatesHtml=candidates.map((m,i)=>{
          const pct=Math.round(m.score*100);
          const cls=m.score>=0.8?'high':m.score>=0.6?'mid':'low';
          return `<div class="cand-row${i===0?' on':''}" data-idx="${i}"><span class="cand-score ${cls}">${pct}%</span><span class="cand-name">${escapeHtml(m.template_name)}</span></div>`;
        }).join('');
      }
    }catch(_){}

    // 判断显示逻辑
    let templateDisplay='';
    if(template){
      templateDisplay=template;
    } else if(candidates.length>0){
      // 无选定模板但有候选：显示 "疑似XX模板"
      const top=candidates[0]; const topPct=Math.round(top.score*100);
      templateDisplay=`<span style="color:var(--orange)">疑似 ${escapeHtml(top.template_name)} (${topPct}%)</span>`;
    } else {
      templateDisplay='<span style="color:var(--red)">未识别到模板</span>';
    }

    overlay.style.display='flex';
    overlay.innerHTML=`
      <div class="review-box">
        <div class="review-head"><h2>✅ 报告已生成 <small>${S.patient?.name||'-'}</small></h2><div style="font-size:18px;color:${confCol};font-weight:900">${confPct}%</div></div>
        <div class="review-body">
          <div class="review-item"><h3>🩺 模板 <span id="reviewTemplate">${templateDisplay}</span></h3>${candidates.length>0?`<div class="cand-list" id="candList">${candidatesHtml}</div>`:''}</div>
          <div class="review-item"><h3>📖 超声所见</h3><div class="review-text" id="reviewSee">${renderReviewedText(see||'-')}</div></div>
          <div class="review-item"><h3>💊 超声提示</h3><div class="review-text" id="reviewHint"><span class="recognized-value">${escapeHtml(hint||'-')}</span></div></div>
          <div class="review-item"><h3>🔧 建议</h3><div class="review-text" id="reviewRec"><span class="recognized-value">${escapeHtml(rec||'')}</span></div></div>
          <div class="review-item"><h3>🎤 识别原文</h3><div class="review-text" style="font-size:16px;color:var(--muted)">${escapeHtml(src.slice(0,200))}</div></div>
        </div>
        <div class="review-foot">
          <button class="btn btn-ghost" id="reviewExtraBtn">➕ 补充一句</button>
          <button class="btn btn-ghost" id="reviewEditBtn">📝 编辑</button>
          <button class="btn btn-blue" id="reviewDoneBtn">✅ 确认完成</button>
        </div>
      </div>`;

    // 候选模板点击切换
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

    $('reviewExtraBtn').addEventListener('click',()=>{overlay.style.display='none';S.appendMode=true;show('screenDirector');resetRecordUI();$('recordHint').textContent='补充一句后自动重新生成';});
    $('reviewEditBtn').addEventListener('click',()=>{
      const ta=document.createElement('textarea');
      ta.value=(rd.study_see||'').replace(/<[^>]+>/g,'');
      ta.style.cssText='width:100%;min-height:160px;font-size:18px;padding:12px;border-radius:14px;background:rgba(15,23,42,.6);border:1px solid var(--line);color:#e5f0ff;font-family:var(--font)';
      overlay.querySelector('.review-body').innerHTML=`<div class="review-item"><h3>📝 修改</h3>${ta.outerHTML}</div><div class="review-item"><h3>💊 提示</h3><div class="review-text"><span class="recognized-value">${escapeHtml(hint||'-')}</span></div></div>`;
      overlay.querySelector('.review-foot').innerHTML=`<button class="btn btn-ghost" onclick="document.getElementById('reviewOverlay').style.display='none'">取消</button><button class="btn btn-blue" id="reviewSaveEditBtn">💾 保存</button>`;
      $('reviewSaveEditBtn').addEventListener('click',async()=>{try{const d=await api('POST','/api/structure',{text:ta.value,exam_type:S.patient?.exam_type||'腹部超声'});if(d.success){overlay.style.display='none';showReview(d);}else toast('保存失败',true);}catch(e){toast(e.message,true);}});
    });
    $('reviewDoneBtn').addEventListener('click',async()=>{overlay.style.display='none';resetRecordUI();await loadQueue();show('screenList');toast(`${S.patient?.name||''} 确认完成`);});
  }

  function toast(msg,error=false,color='') {
    const el=$('toast');el.textContent=msg;
    el.style.borderColor=error?'rgba(251,113,133,.55)':(color||'rgba(56,189,248,.35)');
    el.classList.add('on');setTimeout(()=>el.classList.remove('on'),2600);
  }
})();
