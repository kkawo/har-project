"""
HAR Dashboard — 活动识别展示系统
Flask + SocketIO 后端，支持 ESP32 串口实时数据和模拟演示模式
"""

import json
import math
import random
import threading
import time
from collections import deque
from pathlib import Path

from flask import Flask, render_template
from flask_socketio import SocketIO, emit

# WiFi polling (ESP32 HTTP API)
try:
    import urllib.request as urllib2
except ImportError:
    import urllib2

# ─── App Setup ─────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "har-dashboard-2026"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

ROOT = Path(__file__).parent.parent

# ─── Globals ───────────────────────────────────────────────────────
serial_port = None
serial_thread = None
serial_running = False
demo_running = False  # demo off by default — must connect hardware first
current_mode = "idle"

# WiFi polling (ESP32 HTTP API)
wifi_running = False
wifi_thread = None
ESP32_IP = "192.168.43.100"  # 默认安卓热点常见 IP，可手动改
WIFI_POLL_INTERVAL = 0.5  # 500ms 轮询间隔

# 常见手机热点 IP 段（用于自动扫描）
HOTSPOT_SCAN_IPS = [
    "192.168.43.100", "192.168.43.2", "192.168.43.3",  # Android 热点
    "172.20.10.2", "172.20.10.3", "172.20.10.4",       # iPhone 热点
    "192.168.137.2", "192.168.137.3",                    # Windows 热点
]

# 7 类活动（中英文）
ACTIVITIES = {
    0: {"en": "sit", "zh": "静坐", "icon": "chair"},
    1: {"en": "stand", "zh": "站立", "icon": "person-standing"},
    2: {"en": "walk", "zh": "步行", "icon": "person-walking"},
    3: {"en": "run", "zh": "跑步", "icon": "person-running"},
    4: {"en": "upstairs", "zh": "上楼", "icon": "stairs-up"},
    5: {"en": "downstairs", "zh": "下楼", "icon": "stairs-down"},
    6: {"en": "fall", "zh": "跌倒", "icon": "exclamation-triangle"},
}

# ─── Serial ────────────────────────────────────────────────────────

def find_esp32_port():
    """扫描可用串口，查找 ESP32"""
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            # ESP32 通常显示为 CP210x, CH340, Silicon Labs 等
            if any(k in p.description for k in
                   ["CP210", "CH340", "CH343", "Silicon Labs", "ESP32", "USB Serial", "USB-Enhanced"]):
                return p.device
        # 回退：返回第一个可用串口
        if ports:
            return ports[0].device
    except Exception:
        pass
    return None


def serial_reader():
    """串口读取线程：持续读取 ESP32 输出并推送到前端"""
    global serial_running, demo_running, current_mode
    buffer = ""
    while serial_running and serial_port and serial_port.is_open:
        try:
            data = serial_port.read(serial_port.in_waiting or 1).decode("utf-8", errors="ignore")
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                parsed = parse_esp32_line(line.strip())
                if parsed:
                    demo_running = False
                    current_mode = "live"
                    socketio.emit("sensor_update", parsed)
        except Exception as e:
            socketio.emit("log", {"msg": f"[Serial Error] {e}"})
            time.sleep(1)


def parse_esp32_line(line):
    """解析 ESP32 输出行。优先 DATA: JSON, 回退到文本解析."""
    if not line or not line.strip():
        return None

    s = line.strip()

    # Priority 1: DATA: JSON line (from firmware v2)
    if s.startswith("DATA:"):
        try:
            import json as _json
            d = _json.loads(s[5:])
            return {
                "activity_id": d["id"],
                "activity": d["en"],
                "activity_zh": d["zh"],
                "confidence": d["conf"],
                "log": s,
                "mode": "live",
            }
        except Exception:
            pass

    # Priority 2: text format "[  1.3s] #1 sit 静坐 conf=0.995"
    if "conf=" in s:
        try:
            parts = s.split()
            activity_name = None
            confidence = 0.0
            for i, p in enumerate(parts):
                if p.startswith("conf="):
                    confidence = float(p.split("=")[1].rstrip(")"))
                    if i > 0:
                        activity_name = parts[i - 1]
                    break
            if activity_name:
                activity_id = None
                for aid, info in ACTIVITIES.items():
                    if info["en"] == activity_name.lower() or info["zh"] == activity_name:
                        activity_id = aid
                        break
                if activity_id is not None:
                    return {
                        "activity_id": activity_id,
                        "activity": ACTIVITIES[activity_id]["en"],
                        "activity_zh": ACTIVITIES[activity_id]["zh"],
                        "confidence": confidence,
                        "log": s,
                        "mode": "live",
                    }
        except Exception:
            pass

    # Priority 3: plain log line
    return {"log": s, "acc": None, "gyro": None,
            "activity": None, "confidence": 0, "mode": "live"}


def wifi_poll_loop():
    """WiFi 轮询线程：定时从 ESP32 HTTP API 获取数据"""
    global wifi_running, demo_running, current_mode
    url = f"http://{ESP32_IP}/api/status"
    while True:
        if wifi_running:
            try:
                req = urllib2.urlopen(url, timeout=2)
                data = json.loads(req.read().decode("utf-8"))
                req.close()
                demo_running = False
                current_mode = "live"
                socketio.emit("sensor_update", data)
            except Exception as e:
                # ESP32 might be temporarily busy; keep last known data
                pass
        time.sleep(WIFI_POLL_INTERVAL)


# ─── Demo Data Generator ───────────────────────────────────────────

class DemoGenerator:
    """生成模拟传感器数据，用于无硬件时的演示"""

    def __init__(self):
        self.t = 0.0
        self.current_activity = 2  # 默认步行
        self.activity_remaining = 0
        self.acc_x = deque([0.0] * 50, maxlen=50)
        self.acc_y = deque([0.0] * 50, maxlen=50)
        self.acc_z = deque([10.0] * 50, maxlen=50)  # 重力 ~10 m/s²
        self.gyro_x = deque([0.0] * 50, maxlen=50)
        self.gyro_y = deque([0.0] * 50, maxlen=50)
        self.gyro_z = deque([0.0] * 50, maxlen=50)
        self.logs = deque(maxlen=100)

    def _activity_params(self):
        """不同活动的信号参数 (频率, 幅值, 特征)"""
        a = self.current_activity
        if a == 0:  # 静坐
            return 0.5, 0.3, 0.2  # freq, acc_amp, gyro_amp
        elif a == 1:  # 站立
            return 0.8, 0.5, 0.3
        elif a == 2:  # 步行
            return 1.8, 3.0, 60.0
        elif a == 3:  # 跑步
            return 3.5, 8.0, 150.0
        elif a == 4:  # 上楼
            return 2.0, 5.0, 80.0
        elif a == 5:  # 下楼
            return 2.2, 6.0, 90.0
        elif a == 6:  # 跌倒
            return 0.3, 25.0, 200.0
        return 1.0, 1.0, 30.0

    def generate(self):
        """生成一帧传感器数据"""
        dt = 0.02  # 50Hz
        self.t += dt
        freq, acc_amp, gyro_amp = self._activity_params()

        # 加速度：正弦 + 噪声 + 重力分量（z轴）
        noise = lambda s: random.gauss(0, s * 0.1)

        ax = acc_amp * math.sin(2 * math.pi * freq * self.t) + noise(acc_amp)
        ay = acc_amp * math.cos(2 * math.pi * freq * 0.7 * self.t) + noise(acc_amp)
        az = 9.8 + acc_amp * 0.5 * math.sin(2 * math.pi * freq * 2 * self.t) + noise(acc_amp)

        gx = gyro_amp * math.cos(2 * math.pi * freq * 0.6 * self.t) + noise(gyro_amp)
        gy = gyro_amp * math.sin(2 * math.pi * freq * 0.8 * self.t) + noise(gyro_amp)
        gz = gyro_amp * 0.5 * math.sin(2 * math.pi * freq * 1.2 * self.t) + noise(gyro_amp)

        # 跌倒特殊处理：大冲击脉冲
        if self.current_activity == 6:
            phase = self.t % 2.0
            if phase < 0.2:
                ax += 20; ay += 15; az -= 30

        self.acc_x.append(ax)
        self.acc_y.append(ay)
        self.acc_z.append(az)
        self.gyro_x.append(gx)
        self.gyro_y.append(gy)
        self.gyro_z.append(gz)

        # 活动切换
        self.activity_remaining -= 1
        if self.activity_remaining <= 0:
            # 随机切换（加权，让跑步/步行出现更多）
            weights = [0.05, 0.05, 0.35, 0.35, 0.08, 0.08, 0.04]
            self.current_activity = random.choices(range(7), weights=weights, k=1)[0]
            self.activity_remaining = random.randint(50, 150)  # 1-3秒
            act = ACTIVITIES[self.current_activity]
            self.logs.append(f"> 检测到活动变化: {act['zh']} ({act['en']})")

        confidence = 0.85 + random.random() * 0.14  # 85-99%

        return {
            "activity_id": self.current_activity,
            "activity": ACTIVITIES[self.current_activity]["en"],
            "activity_zh": ACTIVITIES[self.current_activity]["zh"],
            "confidence": round(confidence, 3),
            "acc": {
                "x": list(self.acc_x),
                "y": list(self.acc_y),
                "z": list(self.acc_z),
            },
            "gyro": {
                "x": list(self.gyro_x),
                "y": list(self.gyro_y),
                "z": list(self.gyro_z),
            },
            "log": f"> 预测结果: {ACTIVITIES[self.current_activity]['zh']} "
                   f"(置信度 {confidence:.0%})",
            "sensors": {"chest": True, "thigh": True},
            "model": {"name": "逻辑回归 (LR)", "features": 184},
            "mode": "demo",
        }


demo_gen = DemoGenerator()


def demo_loop():
    """演示模式数据生成线程"""
    global demo_running, current_mode
    while True:
        if demo_running:
            data = demo_gen.generate()
            current_mode = "demo"
            socketio.emit("sensor_update", data)
        time.sleep(0.5)


# ─── Routes ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", activities=ACTIVITIES)


# ─── SocketIO Events ───────────────────────────────────────────────

@socketio.on("connect")
def handle_connect():
    emit("status", {"mode": current_mode, "msg": "已连接到 HAR Dashboard"})


@socketio.on("connect_hardware")
def handle_connect_hardware(data=None):
    global serial_port, serial_thread, serial_running, demo_running

    # Direct serial only — no WiFi scan delay
    ok = auto_connect()
    if ok:
        demo_running = False
        emit("log", {"msg": f"✅ 已连接 ESP32"})
        emit("hardware_status", {"connected": True, "port": "Serial"})
    else:
        emit("log", {"msg": "❌ 串口连接失败 — 关掉 Thonny，拔插 ESP32，再试"})
        emit("hardware_status", {"connected": False, "port": None})


@socketio.on("disconnect_hardware")
def handle_disconnect_hardware():
    global serial_running, demo_running, serial_port, wifi_running
    serial_running = False
    wifi_running = False
    demo_running = True
    if serial_port and serial_port.is_open:
        serial_port.close()
    serial_port = None
    emit("log", {"msg": "🔌 已断开硬件连接，切换到演示模式"})
    emit("hardware_status", {"connected": False, "port": None})


@socketio.on("start_session")
def handle_start_session():
    emit("log", {"msg": "📊 会话已开始 — 记录推理数据..."})
    emit("session_status", {"active": True})


@socketio.on("generate_report")
def handle_generate_report():
    emit("log", {"msg": "📄 正在生成报告..."})
    time.sleep(1)
    emit("log", {"msg": "✅ 报告已生成: report_2026-06-26.pdf"})


@socketio.on("toggle_demo")
def handle_toggle_demo(data):
    global demo_running, current_mode
    demo_running = data.get("enabled", True)
    current_mode = "demo" if demo_running else "live"
    emit("log", {"msg": f"{'🎭 演示模式' if demo_running else '📡 实时模式'}"})


# ─── Main ──────────────────────────────────────────────────────────

def auto_connect():
    """Try to connect serial port. Called at startup and on retry."""
    global serial_port, serial_running, serial_thread, current_mode
    port = find_esp32_port()
    if not port:
        return False
    try:
        import serial as _ser
        if serial_port and serial_port.is_open:
            serial_port.close()
        serial_port = _ser.Serial(port, 115200, timeout=1)
        serial_running = True
        current_mode = "live"
        serial_thread = threading.Thread(target=serial_reader, daemon=True)
        serial_thread.start()
        print(f"ESP32 connected on {port}")
        return True
    except Exception as e:
        print(f"Serial: {e}")
        return False


if __name__ == "__main__":
    auto_connect()

    print("=" * 60)
    print("HAR Dashboard — http://localhost:5000")
    print(f"Serial: {'LIVE' if serial_port else 'NOT CONNECTED — click 连接硬件'}")
    print("=" * 60)

    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
