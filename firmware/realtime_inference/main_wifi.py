"""
HAR WiFi Inference Firmware for ESP32-S3.
Connects to phone hotspot via WiFi STA — access from phone/PC on same network.

Features:
  - WiFi STA mode (connect to phone hotspot)
  - Real-time HAR inference (6-axis MPU6050, 2.56s window, 50% overlap)
  - HTTP server on port 80: / (status page) and /api/status (JSON)
  - Works with dashboard/app.py wireless mode
  - LED: Yellow=connecting, Green=connected, Red=failed

Usage:
  1. Set WIFI_SSID / WIFI_PASS to your phone hotspot
  2. Upload main_wifi.py + model_params.py to ESP32
  3. Power ESP32 via power bank, wear on body
  4. ESP32 connects to phone hotspot → shows IP in serial
  5. Phone/PC on same hotspot → open browser to http://<ESP32_IP>
"""

from machine import Pin, SoftI2C
import struct

# ═══════════════════════════════════════════════════════════════════
# EARLY I2C TEST — before ANY other imports
# ═══════════════════════════════════════════════════════════════════
_test_i2c = SoftI2C(sda=Pin(17), scl=Pin(18), freq=100000)
_test_who = _test_i2c.readfrom_mem(0x68, 0x75, 1)[0]
print(f"EARLY WHO_AM_I: 0x{_test_who:02X}")
_test_d = _test_i2c.readfrom_mem(0x68, 0x3B, 14)
_test_az = struct.unpack(">h", bytes(_test_d[4:6]))[0]
print(f"EARLY ACCEL_Z: {_test_az}")

import network, socket, neopixel, struct, math, gc, time

# ═══════════════════════════════════════════════════════════════════
# Hardware
# ═══════════════════════════════════════════════════════════════════
np = neopixel.NeoPixel(Pin(48), 1)
MPU_ADDR = 0x68
ACCL_SENS, GYRO_SENS = 4096.0, 16.4    # ±8g, ±2000°/s (match offline logger)
GRAVITY = 9.80665

i2c = None  # Created in init_mpu()

# ═══════════════════════════════════════════════════════════════════
# WiFi STA — connect to phone hotspot
# ═══════════════════════════════════════════════════════════════════
WIFI_SSID = "YOUR_HOTSPOT_NAME"     # ← CHANGE to your phone hotspot name
WIFI_PASS = "YOUR_HOTSPOT_PASSWORD" # ← CHANGE to your phone hotspot password
ESP32_IP = "0.0.0.0"     # Set after WiFi connects


def wifi_connect():
    """Connect to WiFi hotspot. Returns True on success."""
    global ESP32_IP
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    print(f"WiFi connecting to {WIFI_SSID}...")
    np[0] = (40, 40, 0); np.write()  # Yellow = connecting
    wlan.connect(WIFI_SSID, WIFI_PASS)
    for _ in range(30):  # 15 second timeout
        if wlan.isconnected():
            ESP32_IP = wlan.ifconfig()[0]
            print(f"WiFi OK! IP: {ESP32_IP}")
            np[0] = (0, 40, 0); np.write()  # Green = connected
            return True
        time.sleep_ms(500)
    print("WiFi FAILED")
    np[0] = (40, 0, 0); np.write()  # Red = failed
    return False

# ═══════════════════════════════════════════════════════════════════
# Sensor ring buffer (MUST be defined before HTTP functions)
# ═══════════════════════════════════════════════════════════════════
sensor_ring = [(0.0,)*6] * 200
sensor_ring_idx = 0

# ═══════════════════════════════════════════════════════════════════
# Import model
# ═══════════════════════════════════════════════════════════════════
print("Loading model...")
np[0] = (40, 0, 0); np.write()

from model_params import (
    N_CLASSES, N_FEATURES, ACTIVITIES, COEF, INTERCEPT,
    SCALER_MEAN, SCALER_STD, ACC_BIAS, ACC_SCALE,
)
print(f"Model: {N_FEATURES}feat, {N_CLASSES}class, {gc.mem_free()}B free")
np[0] = (0, 40, 0); np.write()

# ═══════════════════════════════════════════════════════════════════
# Activity names (Chinese)
# ═══════════════════════════════════════════════════════════════════
ACT_ZH = {0: "静坐", 1: "站立", 2: "步行", 3: "跑步",
          4: "上楼", 5: "下楼", 6: "跌倒"}

LED_COLORS = {
    0: (0,0,255), 1:(0,255,255), 2:(0,255,0), 3:(255,255,0),
    4: (255,165,0), 5:(128,0,255), 6:(255,0,0),
}

# ═══════════════════════════════════════════════════════════════════
# Sensor I/O
# ═══════════════════════════════════════════════════════════════════

def mpu_read():
    for retry in range(3):
        try:
            d = i2c.readfrom_mem(MPU_ADDR, 0x3B, 14)
            ax = struct.unpack(">h", d[0:2])[0] / ACCL_SENS * GRAVITY
            ay = struct.unpack(">h", d[2:4])[0] / ACCL_SENS * GRAVITY
            az = struct.unpack(">h", d[4:6])[0] / ACCL_SENS * GRAVITY
            gx = struct.unpack(">h", d[8:10])[0] / GYRO_SENS
            gy = struct.unpack(">h", d[10:12])[0] / GYRO_SENS
            gz = struct.unpack(">h", d[12:14])[0] / GYRO_SENS
            ax = (ax - ACC_BIAS[0]) * ACC_SCALE[0]
            ay = (ay - ACC_BIAS[1]) * ACC_SCALE[1]
            az = (az - ACC_BIAS[2]) * ACC_SCALE[2]
            return ax, ay, az, gx, gy, gz
        except Exception as e:
            if retry == 2:
                raise e
            time.sleep_ms(10)

# ═══════════════════════════════════════════════════════════════════
# Feature helpers (sorted-free)
# ═══════════════════════════════════════════════════════════════════

def _mean(x):
    s = 0.0; n = len(x)
    for v in x: s += v
    return s / n

def _std(x, mu=None):
    if mu is None: mu = _mean(x)
    s = 0.0; n = len(x)
    for v in x: d = v - mu; s += d * d
    return math.sqrt(s / n)

def _skew(x, mu=None, sigma=None):
    if mu is None: mu = _mean(x)
    if sigma is None: sigma = _std(x, mu)
    if sigma == 0: return 0.0
    s = 0.0; n = len(x)
    for v in x: d = (v-mu)/sigma; s += d*d*d
    return s/n

def _kurtosis(x, mu=None, sigma=None):
    if mu is None: mu = _mean(x)
    if sigma is None: sigma = _std(x, mu)
    if sigma == 0: return 0.0
    s = 0.0; n = len(x)
    for v in x: d = (v-mu)/sigma; s += d*d*d*d
    return s/n - 3.0

def _zcr(x, mu=None):
    if mu is None: mu = _mean(x)
    c = 0
    for i in range(1, len(x)):
        if (x[i] - mu >= 0) != (x[i-1] - mu >= 0): c += 1
    return c / (len(x)-1) if len(x) > 1 else 0.0

def _acorr1(x, mu=None):
    if mu is None: mu = _mean(x)
    n = len(x); num = 0.0; den = 0.0
    for i in range(n-1): num += (x[i]-mu)*(x[i+1]-mu)
    for i in range(n): den += (x[i]-mu)*(x[i]-mu)
    return num/den if den != 0 else 0.0

def time_features(sig):
    n = len(sig)
    if n == 0: return [0.0]*14
    mu = _mean(sig)
    sigma = _std(sig, mu)
    var = sigma * sigma
    rms = math.sqrt(sum(v*v for v in sig)/n)
    mx = max(sig); mn = min(sig); ptp = mx - mn
    med = mu
    sk = _skew(sig, mu, sigma)
    ku = _kurtosis(sig, mu, sigma)
    ir = 1.349 * sigma
    sma = sum(abs(v) for v in sig)/n
    zc = _zcr(sig, mu)
    ac = _acorr1(sig, mu)
    # Order MUST match CSV: mean,std,var,rms,ptp,max,min,median,skew,kurtosis,zcr,sma,iqr,acorr
    return [mu, sigma, var, rms, ptp, mx, mn, med, sk, ku, zc, sma, ir, ac]

def extract_84_features(window):
    """Extract 84 features: 14 time stats x 6 axes (acc+gyro, no mag)."""
    fs = []
    for ch in range(6):  # ax, ay, az, gx, gy, gz only
        sig = [window[i][ch] for i in range(128)]
        fs.extend(time_features(sig))
    return fs  # 14*6 = 84, matches N_FEATURES

def predict(features):
    x = [0.0] * N_FEATURES
    for i in range(N_FEATURES):
        if SCALER_STD[i] != 0:
            x[i] = (features[i] - SCALER_MEAN[i]) / SCALER_STD[i]
    logits = [0.0] * N_CLASSES
    for c in range(N_CLASSES):
        s = INTERCEPT[c]; row = COEF[c]
        for i in range(N_FEATURES): s += x[i] * row[i]
        logits[c] = s
    mx = max(logits)
    exps = [0.0]*N_CLASSES; exp_sum = 0.0
    for c in range(N_CLASSES):
        e = math.exp(logits[c] - mx); exps[c] = e; exp_sum += e
    probs = [e/exp_sum if exp_sum > 0 else 1.0/N_CLASSES for e in exps]
    best_c, best_p = 0, probs[0]
    second_c, second_p = 0, 0.0
    for c in range(N_CLASSES):
        if probs[c] > best_p:
            second_c, second_p = best_c, best_p
            best_c, best_p = c, probs[c]
        elif probs[c] > second_p:
            second_c, second_p = c, probs[c]
    return best_c, best_p, second_c, second_p

# ═══════════════════════════════════════════════════════════════════
# HTTP Server (non-blocking, polled in main loop)
# ═══════════════════════════════════════════════════════════════════

HTTP_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta http-equiv="refresh" content="2">
<title>HAR Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;
     display:flex;flex-direction:column;align-items:center;justify-content:center;
     min-height:100vh;padding:20px}
.card{background:#1e293b;border-radius:16px;padding:32px 24px;text-align:center;
      box-shadow:0 4px 24px rgba(0,0,0,.4);max-width:340px;width:100%}
.dot{width:80px;height:80px;border-radius:50%;margin:0 auto 20px;
     box-shadow:0 0 40px rgba(0,200,83,.4);transition:all .5s}
.activity{font-size:36px;font-weight:800;margin:8px 0;letter-spacing:2px}
.conf{font-size:18px;color:#94a3b8;margin:8px 0}
.conf span{color:#22c55e;font-weight:700;font-size:24px}
.model{font-size:12px;color:#64748b;margin-top:16px}
.log{font-size:11px;color:#475569;margin-top:4px}
.bottom{font-size:11px;color:#334155;margin-top:20px}
</style>
</head>
<body>
<div class="card">
  <div class="dot" style="background:RGB_COLOR;"></div>
  <div class="activity">ACT_NAME</div>
  <div class="conf">置信度 <span>CONF_VAL%</span></div>
  <div class="model">LR · 184特征 · 6轴IMU</div>
  <div class="log">WiFi: WIFI_SSID · IP: ESP32_IP</div>
</div>
<div class="bottom">每2秒自动刷新 | ESP32-S3 实时推理</div>
</body>
</html>"""

# Global state for HTTP responses
http_socket = None
last_result = {"activity_id": -1, "confidence": 0.0}


def http_init():
    global http_socket
    try:
        http_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        http_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        http_socket.bind((ESP32_IP, 80))  # Bind to actual STA IP, not 0.0.0.0
        http_socket.listen(1)
        http_socket.setblocking(False)
        print("HTTP server on", ESP32_IP + ":80")
    except Exception as e:
        print("HTTP init err:", e)
        http_socket = None


def http_poll():
    """Check for and handle one HTTP request (non-blocking)."""
    global http_socket
    if http_socket is None:
        return
    try:
        conn, addr = http_socket.accept()
    except OSError:
        return  # No connection waiting

    try:
        conn.settimeout(2)
        req = conn.recv(512).decode('utf-8', 'ignore')
        if not req:
            conn.close(); return

        # Parse request line
        path = "/"
        try:
            first_line = req.split('\r\n')[0]
            path = first_line.split(' ')[1]
        except:
            pass

        if path == "/api/status":
            # JSON API response
            body = json_api_response()
            resp = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json; charset=utf-8\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            )
        else:
            # HTML page
            body = html_response()
            resp = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            )

        conn.send(resp.encode())
        conn.send(body)
    except Exception as e:
        pass
    finally:
        try:
            conn.close()
        except:
            pass
    gc.collect()


def html_response():
    r = last_result
    cid = r["activity_id"]
    conf = r["confidence"]

    if 0 <= cid <= 6:
        name = ACT_ZH[cid]
        color = LED_COLORS[cid]
        rgb_str = "rgb(%d,%d,%d)" % color
    else:
        name = "等待中"
        rgb_str = "rgb(100,100,100)"

    conf_pct = int(conf * 100)
    html = HTTP_HTML.replace("RGB_COLOR", rgb_str)
    html = html.replace("ACT_NAME", name)
    html = html.replace("CONF_VAL", str(conf_pct))
    html = html.replace("WIFI_SSID", WIFI_SSID)
    html = html.replace("ESP32_IP", ESP32_IP)
    return html.encode('utf-8')


def json_api_response():
    """Return JSON with current result + recent sensor data."""
    r = last_result
    cid = r["activity_id"]
    name_en = ACTIVITIES.get(cid, "unknown") if 0 <= cid <= 6 else "unknown"
    name_zh = ACT_ZH.get(cid, "未知") if 0 <= cid <= 6 else "未知"

    # Build sensor arrays (last 50 samples from ring buffer)
    acc_x, acc_y, acc_z = [], [], []
    gyro_x, gyro_y, gyro_z = [], [], []
    n = len(sensor_ring)
    for i in range(max(0, n-50), n):
        s = sensor_ring[i % 200]
        acc_x.append(s[0]); acc_y.append(s[1]); acc_z.append(s[2])
        gyro_x.append(s[3]); gyro_y.append(s[4]); gyro_z.append(s[5])

    # Manual JSON (no json module in MicroPython or limited)
    def arr_json(a):
        return "[" + ",".join(f"{v:.2f}" for v in a) + "]"

    j = (
        '{"activity_id":' + str(cid)
        + ',"activity":"' + name_en + '"'
        + ',"activity_zh":"' + name_zh + '"'
        + ',"confidence":' + str(round(conf, 3))
        + ',"acc":{"x":' + arr_json(acc_x)
        + ',"y":' + arr_json(acc_y)
        + ',"z":' + arr_json(acc_z) + '}'
        + ',"gyro":{"x":' + arr_json(gyro_x)
        + ',"y":' + arr_json(gyro_y)
        + ',"z":' + arr_json(gyro_z) + '}'
        + ',"sensors":{"chest":true,"thigh":true}'
        + ',"model":{"name":"LR","features":' + str(N_FEATURES) + '}'
        + ',"mode":"live"}'
    )
    return j.encode('utf-8')


def add_sensor_sample(sample):
    global sensor_ring_idx
    sensor_ring[sensor_ring_idx % 200] = sample
    sensor_ring_idx += 1


# ═══════════════════════════════════════════════════════════════════
# MPU6050 Init
# ═══════════════════════════════════════════════════════════════════

def init_mpu():
    global i2c
    i2c = SoftI2C(sda=Pin(17), scl=Pin(18), freq=100000)

    who = i2c.readfrom_mem(MPU_ADDR, 0x75, 1)[0]
    print(f"WHO_AM_I: 0x{who:02X}")

    # Wake up + configure to match offline logger (±8g, ±2000°/s, 50Hz)
    i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')  # PWR_MGMT1: wake
    time.sleep_ms(50)
    i2c.writeto_mem(MPU_ADDR, 0x19, b'\x13')  # SMPLRT_DIV: 50Hz
    i2c.writeto_mem(MPU_ADDR, 0x1A, b'\x06')  # CONFIG: DLPF 5Hz
    i2c.writeto_mem(MPU_ADDR, 0x1C, b'\x10')  # ACCEL_CONFIG: ±8g
    i2c.writeto_mem(MPU_ADDR, 0x1B, b'\x18')  # GYRO_CONFIG: ±2000°/s
    time.sleep_ms(50)

    d = i2c.readfrom_mem(MPU_ADDR, 0x3B, 14)
    ax_r = struct.unpack(">h", bytes(d[0:2]))[0]
    ay_r = struct.unpack(">h", bytes(d[2:4]))[0]
    az_r = struct.unpack(">h", bytes(d[4:6]))[0]
    print(f"ACCEL: ax={ax_r} ay={ay_r} az={az_r}")
    if ax_r == 0 and ay_r == 0 and az_r == 0:
        raise RuntimeError("MPU6050 zeros after wake")
    print("MPU6050 OK")


# ═══════════════════════════════════════════════════════════════════
# LED helper
# ═══════════════════════════════════════════════════════════════════

def show_led(cid, conf):
    color = LED_COLORS.get(cid, (255, 255, 255))
    if cid == 6:  # Fall — flash red
        for _ in range(2):
            np[0] = color; np.write(); time.sleep_ms(120)
            np[0] = (0, 0, 0); np.write(); time.sleep_ms(120)
    else:
        r = int(color[0] * min(conf, 1.0))
        g = int(color[1] * min(conf, 1.0))
        b = int(color[2] * min(conf, 1.0))
        np[0] = (r, g, b); np.write()


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

WINDOW_SIZE, STRIDE, INTERVAL_MS = 128, 64, 20

def main():
    global last_result

    print("=" * 40)
    print("HAR WiFi Inference")
    print("SSID:", WIFI_SSID, "| IP:", ESP32_IP)
    print("Features:", N_FEATURES, "| Classes:", N_CLASSES)
    print("Free:", gc.mem_free())
    print("=" * 40)

    # ── Stage 1: Init MPU6050 (brief blue = starting) ──
    np[0] = (0, 0, 10); np.write()
    for attempt in range(5):
        try:
            init_mpu()
            break
        except Exception as e:
            print(f"init_mpu attempt {attempt+1} failed: {e}")
            np[0] = (20, 0, 20); np.write()  # Purple = retrying
            time.sleep_ms(500)
    else:
        # All attempts failed — flash red fast then stop
        for _ in range(10):
            np[0] = (40, 0, 0); np.write(); time.sleep_ms(100)
            np[0] = (0, 0, 0); np.write(); time.sleep_ms(100)
        return  # Halt — watchdog will reboot

    # ── Stage 2: Connect WiFi ──
    np[0] = (40, 40, 0); np.write()  # Yellow = connecting
    wifi_ok = wifi_connect()

    # ── Stage 3: HTTP server ──
    if wifi_ok:
        np[0] = (0, 10, 10); np.write()  # Cyan = init HTTP
        http_init()
    else:
        print("WiFi failed — HTTP disabled")

    # Flash white x3 = ready
    np[0] = (0, 0, 0); np.write(); time.sleep_ms(300)
    for _ in range(3):
        np[0] = (20, 20, 20); np.write(); time.sleep_ms(200)
        np[0] = (0, 0, 0); np.write(); time.sleep_ms(200)

    print("READY. Open http://" + ESP32_IP + " on phone/PC")

    buffer = [(0.0,)*6] * WINDOW_SIZE
    buf_idx, samples, next_infer = 0, 0, WINDOW_SIZE  # Wait for full buffer
    last_t = time.ticks_ms()
    infer_count = 0
    pred_history = [-1] * 5  # Temporal smoothing: last 5 predictions
    hist_idx = 0

    while True:
        # ── Read MPU6050 (6ch) ──
        try:
            ax, ay, az, gx, gy, gz = mpu_read()
            sample = (ax, ay, az, gx, gy, gz)
        except Exception as e:
            print("Read err:", e)
            np[0] = (40, 0, 0); np.write()
            time.sleep_ms(50)
            http_poll()
            continue

        add_sensor_sample(sample[:6])
        buffer[buf_idx] = sample
        buf_idx = (buf_idx + 1) % WINDOW_SIZE
        samples += 1

        # ── Inference trigger ──
        if samples >= next_infer:
            next_infer += STRIDE
            infer_count += 1

            window = []
            for i in range(WINDOW_SIZE):
                window.append(buffer[(buf_idx - WINDOW_SIZE + i) % WINDOW_SIZE])

            try:
                feats = extract_84_features(window)
                cid, conf, cid2, conf2 = predict(feats)

                # Temporal smoothing: majority vote over last N predictions
                pred_history[hist_idx % 5] = cid
                hist_idx += 1
                filled = pred_history[:min(hist_idx, 5)]
                votes = [0] * N_CLASSES
                for p in filled:
                    if p >= 0:
                        votes[p] += 1
                best_vote = 0
                smooth_cid = 0
                for c in range(N_CLASSES):
                    if votes[c] > best_vote:
                        best_vote, smooth_cid = votes[c], c

                last_result = {"activity_id": smooth_cid, "confidence": conf}
                show_led(smooth_cid, conf)

                t_sec = samples / 50.0
                name_en = ACTIVITIES.get(smooth_cid, 'unknown')
                name_zh = ACT_ZH.get(smooth_cid, '?')
                mark = " *** FALL ***" if smooth_cid == 6 else ""
                print(f"[{t_sec:5.1f}s] #{infer_count} {name_en} {name_zh} conf={conf:.3f}{mark}")
                # JSON data line for dashboard parsing
                print('DATA:{"id":%d,"zh":"%s","en":"%s","conf":%.3f}' % (smooth_cid, name_zh, name_en, conf))
            except Exception as e:
                print(f"INFER ERR #{infer_count}: {e}")
                np[0] = (255, 0, 0); np.write(); time.sleep_ms(100)
                np[0] = (0, 0, 0); np.write()

        # ── Handle one HTTP request per loop iteration ──
        http_poll()

        # ── Timing ──
        elapsed = time.ticks_diff(time.ticks_ms(), last_t)
        wait = INTERVAL_MS - elapsed
        if wait > 0:
            time.sleep_ms(wait)
        last_t = time.ticks_ms()


if __name__ == "__main__":
    main()
