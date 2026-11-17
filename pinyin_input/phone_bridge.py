# -*- coding: utf-8 -*-
"""
phone_bridge - 好搭AI派 手机辅助页服务（无 UI 依赖，纯标准库）
功能：在设备局域网内起 HTTP 服务，手机浏览器打开后可直接打字，
  一键推送到设备（设备端轮询 get_text() 取走）。
端口说明：每次 start() 由系统随机分配空闲端口（局域网内可能有多台设备，
  固定端口会互相冲突，故不提供固定端口选项），实际地址以 self.url 为准。
调用示例：
    from phone_bridge import PhoneBridge
    bridge = PhoneBridge()
    bridge.start()
    print(bridge.url)          # 屏幕上显示该地址/二维码（每次启动都不同）
    while running:
        text = bridge.get_text()   # 每帧轮询，取到手机推送的文本
        if text:
            ime.commit_external(text)
    bridge.stop()
运行环境：Python 3.8+，纯标准库
"""

import html
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_PAGE_TEMPLATE = u'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>好搭AI派 · 手机辅助输入</title>
<style>
  body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
         background:#EAF4FB; color:#17324D; }
  .wrap { max-width:560px; margin:0 auto; padding:16px; }
  h1 { font-size:20px; margin:8px 0 4px; }
  .sub { font-size:13px; color:#5B7A99; margin-bottom:14px; }
  textarea { width:100%; box-sizing:border-box; height:120px; font-size:18px;
             padding:12px; border:2px solid #BBD8EE; border-radius:12px;
             background:#FFFFFF; color:#17324D; resize:none; }
  button { width:100%; margin-top:14px; padding:16px; font-size:20px; font-weight:600;
           border:none; border-radius:999px; background:#2E9BE6; color:#FFFFFF; }
  button:active { background:#1B7FC7; }
  .status { margin-top:12px; font-size:14px; color:#2E9BE6; min-height:20px; text-align:center; }
</style>
</head>
<body>
<div class="wrap">
  <h1>手机辅助输入</h1>
  <div class="sub">内容与设备实时同步，点「发送到设备」覆盖更新</div>
  <textarea id="box" placeholder="已同步设备文字，可在此继续输入...">__TEXT__</textarea>
  <button onclick="send()">发送到设备</button>
  <div class="status" id="status"></div>
</div>
<script>
var PIN = '__PIN__';
var box = document.getElementById('box');
var dirty = false;   // 用户在手机上编辑过则暂停自动同步，发送后恢复
box.addEventListener('input', function() { dirty = true; });
// 未编辑时每 1.5 秒自动同步设备编辑区内容
setInterval(function() {
  if (dirty) { return; }
  fetch('/text').then(function(r) { return r.json(); }).then(function(d) {
    if (!dirty && document.activeElement !== box && box.value !== d.text) {
      box.value = d.text;
    }
  }).catch(function() {});
}, 1500);
function send() {
  var st = document.getElementById('status');
  var text = box.value;
  if (!text.trim()) { st.textContent = '请先输入内容'; return; }
  st.textContent = '发送中...';
  fetch('/send', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text: text, pin: PIN})
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.ok) { st.textContent = '已同步到设备 ✓'; dirty = false; }
    else { st.textContent = '发送失败：' + (d.msg || '未知错误'); }
  }).catch(function() { st.textContent = '网络错误，请确认与设备同一局域网'; });
}
box.addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { send(); }
});
</script>
</body>
</html>'''


class PhoneBridge(object):
    """手机辅助输入桥接服务。start() 后台线程运行，stop() 停止。
    端口每次启动由系统随机分配，start() 成功后 self.port / self.url 才生效。"""

    def __init__(self, pin=None):
        self.port = None            # start() 后由系统随机分配并回填
        self.pin = pin or ''
        self.url = None             # start() 成功后生效
        self._server = None
        self._thread = None
        self._lock = threading.Lock()
        self._latest_text = None    # 待取走文本
        self._current_text = ''     # 设备编辑区当前内容（打开手机页时同步显示）
        self._conn_count = 0        # 手机访问计数

    # ---------- 设备端 API ----------

    def start(self):
        """启动服务（幂等）。返回 True 表示已监听，此时 self.url / self.port 已生效。"""
        if self._server is not None:
            return True
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass  # 静默，不打日志

            def _json(self, obj, code=200):
                body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                with bridge._lock:
                    bridge._conn_count += 1
                if self.path == '/status':
                    self._json({'ok': True, 'device': 'haoda-aipai'})
                elif self.path == '/text':
                    # 手机页轮询：获取设备编辑区最新内容（未编辑时自动刷新）
                    with bridge._lock:
                        current = bridge._current_text
                    self._json({'ok': True, 'text': current or ''})
                else:
                    with bridge._lock:
                        current = bridge._current_text
                    page = (_PAGE_TEMPLATE
                            .replace('__PIN__', bridge.pin)
                            .replace('__TEXT__', html.escape(current or '')))
                    body = page.encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            def do_POST(self):
                if self.path != '/send':
                    self._json({'ok': False, 'msg': 'unknown path'}, 404)
                    return
                try:
                    length = int(self.headers.get('Content-Length', 0) or 0)
                    data = json.loads(self.rfile.read(length).decode('utf-8'))
                except Exception:
                    self._json({'ok': False, 'msg': 'bad request'}, 400)
                    return
                if bridge.pin and data.get('pin') != bridge.pin:
                    self._json({'ok': False, 'msg': 'PIN 不正确'}, 403)
                    return
                text = (data.get('text') or '').strip()
                if not text:
                    self._json({'ok': False, 'msg': 'empty text'}, 400)
                    return
                with bridge._lock:
                    bridge._latest_text = text
                self._json({'ok': True})

        try:
            self._server = ThreadingHTTPServer(('0.0.0.0', 0), Handler)
        except Exception:
            return False
        # 回填系统随机分配的实际端口
        self.port = self._server.server_port
        self.url = 'http://%s:%d' % (self._local_ip(), self.port)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """停止服务"""
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None
            self._thread = None

    def set_current_text(self, text):
        """设备端每帧同步编辑区内容，手机页打开时即显示"""
        with self._lock:
            self._current_text = text or ''

    def get_text(self):
        """取走手机推送的最新文本（取走即清空）；无新文本返回 None"""
        with self._lock:
            text = self._latest_text
            self._latest_text = None
        return text

    def connection_count(self):
        """手机页面被打开过的次数（用于显示连接状态）"""
        with self._lock:
            return self._conn_count

    # ---------- 内部 ----------

    @staticmethod
    def _local_ip():
        """探测本机局域网 IP"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            try:
                return socket.gethostbyname(socket.gethostname())
            except Exception:
                return '127.0.0.1'


if __name__ == '__main__':
    bridge = PhoneBridge()
    if bridge.start():
        print('手机辅助页: %s （Ctrl+C 退出）' % bridge.url)
        try:
            while True:
                text = bridge.get_text()
                if text:
                    print('收到: %s' % text)
                threading.Event().wait(0.2)
        except KeyboardInterrupt:
            pass
        finally:
            bridge.stop()
    else:
        print('服务启动失败（随机端口分配异常）')
