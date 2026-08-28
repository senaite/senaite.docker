/* labgate 采集端界面公共脚本 */

/* 管理接口鉴权令牌：从 localStorage 读取（配置页可设置/清除）。
   留空 = 未启用鉴权或本机直连，按旧行为放行。 */
function apiToken() {
  return localStorage.getItem('labgate_api_token') || '';
}

function apiHeaders(json) {
  var h = json ? { 'Content-Type': 'application/json' } : {};
  var t = apiToken();
  if (t) { h['Authorization'] = 'Bearer ' + t; }
  return h;
}

function toast(message, type) {
  var box = document.getElementById('toast-box');
  if (!box) { return; }
  var el = document.createElement('div');
  el.className = 'toast' + (type === 'error' ? ' err' : '');
  el.textContent = message;
  box.appendChild(el);
  setTimeout(function () { el.remove(); }, 3500);
}

/* HTML 转义：仪器返回的原始行会直接进表格，必须转义后再插入 */
function esc(value) {
  if (value === null || value === undefined) { return ''; }
  return String(value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function apiGet(url, cb) {
  fetch(url, { headers: apiHeaders(false) })
    .then(function (r) { return r.json(); })
    .then(cb)
    .catch(function () { /* 轮询期间的瞬时失败忽略，下一轮会补上 */ });
}

function apiPost(url, data, cb) {
  return fetch(url, {
    method: 'POST',
    headers: apiHeaders(true),
    body: JSON.stringify(data || {})
  }).then(function (r) { return r.json(); }).then(function (d) {
    if (d && d.success === false) { toast(d.message || '操作失败', 'error'); return; }
    if (cb) { cb(d); }
  }).catch(function () { toast('请求失败，采集端可能已停止', 'error'); });
}

/* 导航栏右侧的运行状态：模式 / 仪器连接 / 云端连接 */
function refreshNavStatus() {
  apiGet('/api/state', function (d) {
    var el = document.getElementById('nav-status');
    if (!el) { return; }
    var cloud = d.cloud || {};
    var parts = [];
    parts.push('<span class="muted">' + (d.mode === 'manual' ? '手动模式' : '自动模式') + '</span>');
    parts.push(d.connected
      ? '<span class="badge badge-ok">仪器已连接</span>'
      : '<span class="badge badge-off">仪器未连接</span>');
    if (!cloud.leaf_enabled) {
      parts.push('<span class="badge badge-off">云端未配置</span>');
    } else if (cloud.leaf_connected) {
      parts.push('<span class="badge badge-ok">云端已连接</span>');
    } else {
      parts.push('<span class="badge badge-warn">云端断开</span>');
    }
    if (d.stats && d.stats.cache_pending > 0) {
      parts.push('<span class="badge badge-info">待上传 ' + d.stats.cache_pending + '</span>');
    }
    el.innerHTML = parts.join('');
  });
}

document.addEventListener('DOMContentLoaded', function () {
  refreshNavStatus();
  setInterval(refreshNavStatus, 3000);
});
