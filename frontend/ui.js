/**
 * 超声语音报告系统 - UI 渲染组件
 */

const UI = {
  // ===== Toast 通知 =====
  toast(msg, type = 'info') {
    const el = document.createElement('div');
    el.className = 'toast toast-' + type;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => { el.remove(); }, 3000);
  },

  // ===== 模态框 =====
  modal(title, bodyHtml, footerHtml = '') {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay on';
    overlay.innerHTML = `
      <div class="modal">
        <div class="modal-hd"><span>${title}</span><span class="btn-ghost btn" onclick="this.closest('.modal-overlay').remove()">✕</span></div>
        <div class="modal-bd">${bodyHtml}</div>
        ${footerHtml ? `<div class="modal-ft">${footerHtml}</div>` : ''}
      </div>`;
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
    return overlay;
  },

  // ===== 骨架屏 =====
  skeleton(count = 3) {
    return Array(count).fill('<div class="skeleton"></div>').join('');
  },

  loading(text = '加载中...') {
    return `<div class="loading"><div class="spinner"></div>${text}</div>`;
  },

  // ===== 报告渲染 =====
  renderResult(d) {
    const report = d.report || {};
    const see = this._strip(report.study_see || '');
    const hints = (report.study_hint || []).filter(h => h.checked !== false);
    const rec = report.recommendation || '';
    const hasOutput = !!(see || hints.length || rec);

    if (!hasOutput) {
      document.getElementById('rSee').innerHTML = '<span class="text-muted">等待输入...</span>';
      document.getElementById('rHints').innerHTML = '<span class="text-muted">-</span>';
      document.getElementById('rRec').innerHTML = '<span class="text-muted">-</span>';
    } else {
      document.getElementById('rSee').innerHTML = see || '<span class="text-muted">(空)</span>';
      document.getElementById('rHints').innerHTML = hints.length
        ? hints.map(h => `<span class="tag tag-blue" style="margin:2px">${h.diagnosis || h}</span>`).join(' ')
        : '<span class="text-muted">(空)</span>';
      document.getElementById('rRec').innerHTML = rec || '<span class="text-muted">(空)</span>';
    }

    document.getElementById('rMethod').textContent = d.method || '?';
    document.getElementById('rMeta').innerHTML = `
      <div class="kv"><k>方法</k><v>${d.method || '?'}</v></div>
      <div class="kv"><k>模板</k><v>${d.template_used || '?'}</v></div>
      <div class="kv"><k>置信度</k><v><span class="tag ${(d.confidence||0) >= 0.8 ? 'tag-green' : (d.confidence||0) >= 0.6 ? 'tag-orange' : 'tag-red'}">${((d.confidence||0)*100).toFixed(0)}%</span></v></div>
      <div class="kv"><k>耗时</k><v>${d.elapsed_ms || '?'} ms</v></div>
      <div class="kv"><k>警告</k><v>${(d.warnings||[]).join('; ') || '-'}</v></div>
      <div class="kv"><k>ASR原文</k><v style="font-size:11px;color:var(--text-muted)">${((d.sources?.A_asr)||'').slice(0,80)}</v></div>
    `;
  },

  renderTimeline(d, text) {
    const steps = [];
    const method = d.method || '?';
    const template = d.template_used || '?';
    const warnings = d.warnings || [];
    const A = d.sources?.A_asr || text;

    steps.push({ label: 'L0 文本接收', detail: `"${A.slice(0,30)}..."`, ok: true });
    steps.push({ label: 'L0.5 口误过滤', detail: '不对不对/改一下/等一下', ok: true });
    steps.push({ label: 'L1 路由预分类', detail: method.includes('fetal') ? '胎儿' : method.includes('multi') ? '多器官' : '标准', ok: true });

    if (method === 'fetal_template') {
      steps.push({ label: 'L2 胎儿模板', detail: 'fill_fetal_template', ok: true });
    } else if (method === 'converted_fill' || method === 'converted_fill_llm') {
      steps.push({ label: 'L2 模板搜索', detail: template, ok: true });
      steps.push({ label: 'L3 40万引擎', detail: warnings.find(w => w.includes('40万')) ? '触发' : '跳过', ok: true });
      steps.push({ label: 'L4 转换填充', detail: method === 'converted_fill_llm' ? '+LLM补全' : 'fill_converted_template', ok: true });
    } else if (method === 'template_fill') {
      steps.push({ label: 'L2 模板搜索', detail: template, ok: true });
      steps.push({ label: 'L3 LLM填充', detail: '_llm_fill_template', ok: true });
    } else if (method === 'llm_free') {
      steps.push({ label: 'L2 LLM自由生成', detail: '无匹配模板', ok: true });
    }

    steps.push({ label: 'L5 数值保全', ok: true, detail: warnings.find(w => w.includes('数值')) ? '追加' : '无缺失' });
    steps.push({ label: 'L6 验证', ok: !warnings.find(w => w.includes('L5')||w.includes('L6')), detail: warnings.find(w => w.includes('L5')||w.includes('L6')) || '通过' });
    steps.push({ label: 'L7 建议生成', ok: true, detail: '规则' });
    steps.push({ label: 'L8 入库', ok: true, detail: (d.report?.study_hint||[]).length + '条诊断' });

    const el = document.getElementById('tlSteps');
    if (el) {
      el.innerHTML = steps.map(s => `
        <div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--border)">
          <span>${s.ok ? '✅' : '❌'}</span>
          <span style="flex:1;font-size:12px">${s.label}</span>
          <span style="font-size:10px;color:var(--text-muted)">${s.detail}</span>
        </div>
      `).join('');
    }
    const countEl = document.getElementById('tlCount');
    if (countEl) countEl.textContent = steps.length + ' 步';
  },

  renderKB(d) {
    const el = document.getElementById('kbStatus');
    if (!el) return;
    el.innerHTML = `<pre>${JSON.stringify({
      version: d.version || '?',
      api_templates: d.templates || 0,
      api_hotwords: d.asr_hotwords || 0,
      loaded_files: [
        'confusion_dict(170条)', 'confusion_dict_ext(91条)',
        'normal_ranges', 'normal_thresholds', 'ultrasound_value_rules',
        'grading_standards(BI-RADS等)', 'high_risk_signs', 'sex_guard_rules',
        'high_conf_candidates(146条)', 'matching_rules_merged(70条)',
        '更多共37项...'
      ]
    }, null, 2)}</pre>`;
  },

  renderDB(d) {
    const el = document.getElementById('dbStatus');
    if (!el) return;
    el.innerHTML = `<pre>${JSON.stringify({
      total_reports: d.total_reports || 0,
      confirmed: d.confirmed || 0,
      draft: d.draft || 0,
      today: d.today_reports || 0,
      doctors: d.total_doctors || 0,
      patients: d.total_patients || 0,
    }, null, 2)}</pre>`;
  },

  renderHistory(d) {
    const reports = d.reports || [];
    const el = document.getElementById('historyList');
    if (!el) return;
    const countEl = document.getElementById('historyCount');
    if (countEl) countEl.textContent = reports.length + '条';

    if (!reports.length) {
      el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">无记录</div>';
      return;
    }

    let html = '<div class="table-wrap"><table><thead><tr>' +
      '<th>时间</th><th>检查</th><th>诊断</th><th>所见摘要</th><th style="width:50px">操作</th></tr></thead><tbody>';
    reports.forEach(r => {
      const time = (r.created_at || '').slice(0,16) || (r.examdate||'')+' '+(r.examtime||'');
      html += `<tr>
        <td style="font-family:var(--mono);font-size:11px">${time}</td>
        <td>${r.VISCERAS||r.ModuleName||'-'}</td>
        <td>${(r.DIAGNOSIS||'').slice(0,24)}</td>
        <td style="color:var(--text-muted);font-size:11px">${(r.DESCRIBES||'').slice(0,40)}...</td>
        <td><button class="btn btn-ghost btn-sm" onclick="alert('${(r.DESCRIBES||'').replace(/'/g,"\\'").slice(0,200)}')">查看</button></td>
      </tr>`;
    });
    html += `</tbody></table></div><div style="padding:8px 0;font-size:11px;color:var(--text-muted)">显示 ${reports.length} 条</div>`;
    el.innerHTML = html;
  },

  _strip(h) {
    const d = document.createElement('div');
    d.innerHTML = h;
    return d.textContent || d.innerText || '';
  },
};
