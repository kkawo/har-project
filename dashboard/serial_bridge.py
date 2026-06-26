"""
Serial-to-HTTP bridge — reads ESP32 DATA: lines from serial, serves live page.
Usage: python dashboard/serial_bridge.py
Open: http://localhost:5000
"""
import json
import time
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Config ──
PORT = 5000
BAUD = 115200

# ── Shared state ──
state = {
    "id": -1, "zh": "等待中", "en": "unknown", "conf": 0.0,
    "ts": "", "raw": ""
}
state_lock = threading.Lock()

# ── Find ESP32 serial port ──
def find_port():
    try:
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            if any(k in p.description for k in
                   ["CP210", "CH340", "Silicon Labs", "ESP32", "USB Serial"]):
                return p.device
        ports = list(serial.tools.list_ports.comports())
        return ports[0].device if ports else None
    except Exception:
        return None


# ── Serial reader thread ──
def serial_thread(port_name):
    global state
    import serial
    ser = serial.Serial(port_name, BAUD, timeout=1)
    buffer = ""
    while True:
        try:
            chunk = ser.read(ser.in_waiting or 1).decode("utf-8", errors="ignore")
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if line.startswith("DATA:"):
                    try:
                        d = json.loads(line[5:])
                        with state_lock:
                            state["id"] = d["id"]
                            state["zh"] = d["zh"]
                            state["en"] = d["en"]
                            state["conf"] = d["conf"]
                            state["ts"] = time.strftime("%H:%M:%S")
                            state["raw"] = line
                    except Exception:
                        pass
        except Exception as e:
            time.sleep(1)


# ── Color lookup ──
LED_COLORS = [
    (0, 0, 255),     # sit → Blue
    (0, 255, 255),   # stand → Cyan
    (0, 255, 0),     # walk → Green
    (255, 255, 0),   # run → Yellow
    (255, 165, 0),   # upstairs → Orange
    (128, 0, 255),   # downstairs → Purple
    (255, 0, 0),     # fall → Red
]

# ── HTML page ──
HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="1">
<title>HAR Live</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;
     display:flex;flex-direction:column;align-items:center;justify-content:center;
     min-height:100vh;padding:20px}
.card{background:#1e293b;border-radius:20px;padding:40px 32px;text-align:center;
      box-shadow:0 8px 40px rgba(0,0,0,.5);max-width:380px;width:100%}
.dot{width:100px;height:100px;border-radius:50%;margin:0 auto 24px;
     box-shadow:0 0 60px COLOR_GLOW;transition:all .6s}
.name{font-size:48px;font-weight:900;letter-spacing:4px;margin:8px 0}
.conf{font-size:20px;color:#94a3b8;margin:8px 0}
.conf span{color:#22c55e;font-weight:700;font-size:28px}
.info{font-size:13px;color:#475569;margin-top:20px}
.bar{display:flex;justify-content:center;gap:8px;margin-top:16px;flex-wrap:wrap}
.chip{padding:4px 12px;border-radius:12px;font-size:11px;border:1px solid #334155}
.chip.on{background:CHIP_BG;border-color:CHIP_BORDER;color:CHIP_COLOR}
.status{font-size:11px;color:#334155;margin-top:16px}
</style>
</head>
<body>
<div class="card">
  <div class="dot" style="background:COLOR_RGB;"></div>
  <div class="name" style="color:COLOR_RGB;">ACT_NAME</div>
  <div class="conf">置信度 <span>CONF_VAL%</span></div>
  <div class="bar">
    CHIPS
  </div>
  <div class="info">ESP32-S3 · LR 84feat · 6轴IMU</div>
  <div class="status">最后更新: LAST_TS | 串口: SERIAL_PORT</div>
</div>
<script>
// Fallback: SSE for live update without page reload
if(window.EventSource){
  var es=new EventSource("/stream");
  es.onmessage=function(e){
    var d=JSON.parse(e.data);
    document.querySelector(".dot").style.background="rgb("+d.r+","+d.g+","+d.b+")";
    document.querySelector(".dot").style.boxShadow="0 0 60px rgba("+d.r+","+d.g+","+d.b+",0.5)";
    document.querySelector(".name").textContent=d.zh;
    document.querySelector(".name").style.color="rgb("+d.r+","+d.g+","+d.b+")";
    document.querySelector(".conf span").textContent=d.conf+"%";
    document.querySelector(".status").textContent="实时更新: "+d.ts+" | 串口: "+d.port;
    // Update chips
    var chips=document.querySelectorAll(".chip");
    chips.forEach(function(c){c.classList.remove("on")});
    var active=document.getElementById("chip"+d.id);
    if(active)active.classList.add("on");
  }
}
</script>
</body>
</html>"""


def build_html(port_name):
    s = state
    cid = s["id"]
    if 0 <= cid <= 6:
        r, g, b = LED_COLORS[cid]
        name = s["zh"]
        glow = f"rgba({r},{g},{b},0.5)"
        color_rgb = f"rgb({r},{g},{b})"
    else:
        r, g, b = 100, 100, 100
        name = "等待中"
        glow = "rgba(100,100,100,0.3)"
        color_rgb = "rgb(100,100,100)"

    # Activity chips
    names = ["静坐","站立","步行","跑步","上楼","下楼","跌倒"]
    chips = ""
    for i, n in enumerate(names):
        rr, gg, bb = LED_COLORS[i]
        on = " on" if i == cid else ""
        chips += f'<span id="chip{i}" class="chip{on}" style="--c:rgb({rr},{gg},{bb})">● {n}</span> '

    html = HTML.replace("COLOR_RGB", color_rgb)
    html = html.replace("COLOR_GLOW", glow)
    html = html.replace("ACT_NAME", name)
    html = html.replace("CONF_VAL", str(int(s["conf"]*100)))
    html = html.replace("LAST_TS", s["ts"] or "--:--:--")
    html = html.replace("SERIAL_PORT", port_name or "?")
    html = html.replace("CHIPS", chips)
    html = html.replace("CHIP_BG", f"rgba({r},{g},{b},0.2)" if 0<=cid<=6 else "transparent")
    html = html.replace("CHIP_BORDER", f"rgb({r},{g},{b})" if 0<=cid<=6 else "#334155")
    html = html.replace("CHIP_COLOR", f"rgb({r},{g},{b})" if 0<=cid<=6 else "#64748b")
    return html.encode("utf-8")


# ── SSE stream ──
class SSEHandler:
    """Minimal SSE handler for live updates without page refresh."""
    def __init__(self):
        self.clients = []
    def add(self, wfile):
        self.clients.append(wfile)
    def remove(self, wfile):
        if wfile in self.clients: self.clients.remove(wfile)
    def broadcast(self, data):
        dead = []
        for c in self.clients:
            try: c.write(data); c.flush()
            except: dead.append(c)
        for d in dead: self.remove(d)

sse = SSEHandler()


# ── HTTP request handler ──
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass  # quiet

    def do_GET(self):
        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            sse.add(self.wfile)
            # Keep connection open (handled by SSE broadcast)
            while True:
                time.sleep(10)  # keep-alive
        else:
            with state_lock:
                html = build_html(PORT_NAME)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)


# ── SSE broadcast thread ──
def sse_broadcaster():
    while True:
        time.sleep(0.5)  # 500ms update
        with state_lock:
            cid = state["id"]
            if 0 <= cid <= 6:
                r, g, b = LED_COLORS[cid]
                data = json.dumps({
                    "id": cid, "zh": state["zh"], "en": state["en"],
                    "conf": int(state["conf"]*100),
                    "r": r, "g": g, "b": b,
                    "ts": state["ts"], "port": PORT_NAME,
                })
            else:
                data = json.dumps({
                    "id": -1, "zh": "等待中", "en": "unknown",
                    "conf": 0, "r": 100, "g": 100, "b": 100,
                    "ts": "", "port": PORT_NAME,
                })
        sse.broadcast(f"data: {data}\n\n".encode())


# ═══════════════════════════════════════════════════════════════════
PORT_NAME = None

if __name__ == "__main__":
    print("=== HAR Serial Bridge ===")
    PORT_NAME = find_port()
    if not PORT_NAME:
        print("WARN: No ESP32 serial port found! Demo only.")
        PORT_NAME = "(none)"
    else:
        print(f"ESP32 on {PORT_NAME}")
        t = threading.Thread(target=serial_thread, args=(PORT_NAME,), daemon=True)
        t.start()

    # Start SSE broadcaster
    t2 = threading.Thread(target=sse_broadcaster, daemon=True)
    t2.start()

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Open http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDone.")
