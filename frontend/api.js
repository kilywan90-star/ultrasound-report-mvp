/**
 * 超声语音报告系统 - API 封装
 * 统一处理请求/响应/错误
 */

const API = {
  base: '',
  token: '',

  async _fetch(method, path, body) {
    const url = this.base + path;
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body) opts.body = JSON.stringify(body);
    if (this.token) opts.headers['Authorization'] = 'Bearer ' + this.token;

    try {
      const resp = await fetch(url, opts);
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      return await resp.json();
    } catch (e) {
      if (e.name === 'TypeError' && e.message.includes('fetch')) {
        throw new Error('网络错误：无法连接到服务器');
      }
      throw e;
    }
  },

  get(path) { return this._fetch('GET', path); },
  post(path, data) { return this._fetch('POST', path, data); },
  put(path, data) { return this._fetch('PUT', path, data); },
  del(path) { return this._fetch('DELETE', path); },

  // ===== 语音识别 =====
  async uploadAudio(audioBlob, format, options = {}) {
    const form = new FormData();
    form.append('file', audioBlob, `recording.${format || 'webm'}`);
    form.append('doctor', Store.state.doctor || '');
    form.append('exam_type', options.exam_type || document.getElementById('examType')?.value || '腹部超声');
    form.append('run_structure', options.run_structure ? 'true' : 'false');
    const resp = await fetch(this.base + '/api/asr/transcribe', { method: 'POST', body: form });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || '语音识别失败');
    }
    return await resp.json();
  },

  async uploadAudioBase64(base64, format) {
    const blob = await fetch(`data:audio/${format || 'webm'};base64,${base64}`).then(r => r.blob());
    return this.uploadAudio(blob, format || 'webm');
  },
};
