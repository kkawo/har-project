"""
HAR Real-time Inference Firmware for ESP32-S3.

Reads MPU6050 + HMC5883L @ 50Hz into circular buffer (128 samples).
Every 1.28s (50% overlap), extracts 184 non-FFT features, runs a
LogisticRegression classifier, and shows result on NeoPixel LED + serial.

Setup:
  1. Copy main.py + model_params.py to ESP32 (via Thonny/mpremote)
  2. Power on → LED white pulse = ready
  3. Wear on waist, perform activities → watch LED + serial output

LED color map:
  sit=Blue, stand=Cyan, walk=Green, run=Yellow,
  upstairs=Orange, downstairs=Purple, fall=Red(blink)
"""

from machine import Pin, SoftI2C
from time import sleep_ms, ticks_ms, ticks_diff
import neopixel, struct, math

# ─── Hardware ───────────────────────────────────────────────────────
SDA = Pin(17)
SCL = Pin(18)
i2c = SoftI2C(sda=SDA, scl=SCL, freq=400000)
np = neopixel.NeoPixel(Pin(48), 1)
MPU_ADDR, HMC_ADDR = 0x68, 0x1E
ACCL_SENS, GYRO_SENS = 4096.0, 16.4
GRAVITY = 9.80665

from model_params import (
    N_CLASSES, N_FEATURES, ACTIVITIES, COEF, INTERCEPT,
    SCALER_MEAN, SCALER_STD, ACC_BIAS, ACC_SCALE, FEATURE_NAMES,
)

# ══════════════════════════════════════════════════════════════════════
# Sensor I/O
# ══════════════════════════════════════════════════════════════════════

def mpu_read():
    d = i2c.readfrom_mem(MPU_ADDR, 0x3B, 14)
    ax = struct.unpack(">h", d[0:2])[0] / ACCL_SENS * GRAVITY
    ay = struct.unpack(">h", d[2:4])[0] / ACCL_SENS * GRAVITY
    az = struct.unpack(">h", d[4:6])[0] / ACCL_SENS * GRAVITY
    gx = struct.unpack(">h", d[8:10])[0] / GYRO_SENS
    gy = struct.unpack(">h", d[10:12])[0] / GYRO_SENS
    gz = struct.unpack(">h", d[12:14])[0] / GYRO_SENS
    return ax, ay, az, gx, gy, gz


def hmc_read():
    d = i2c.readfrom_mem(HMC_ADDR, 0x03, 6)
    mx = struct.unpack(">h", d[0:2])[0]
    mz = struct.unpack(">h", d[2:4])[0]
    my = struct.unpack(">h", d[4:6])[0]
    sens = 1090.0 / 100.0
    return mx / sens, my / sens, mz / sens


def read_9ch():
    ax, ay, az, gx, gy, gz = mpu_read()
    mx, my, mz = hmc_read()
    ax = (ax - ACC_BIAS[0]) * ACC_SCALE[0]
    ay = (ay - ACC_BIAS[1]) * ACC_SCALE[1]
    az = (az - ACC_BIAS[2]) * ACC_SCALE[2]
    return ax, ay, az, gx, gy, gz, mx, my, mz


# ══════════════════════════════════════════════════════════════════════
# Feature extraction — pure Python (no numpy/scipy)
# ══════════════════════════════════════════════════════════════════════

def _mean(x):
    s = 0.0
    for v in x: s += v
    return s / len(x)


def _std(x, mu=None):
    if mu is None: mu = _mean(x)
    s = 0.0
    for v in x: d = v - mu; s += d * d
    return math.sqrt(s / len(x))


def _median(x):
    y = sorted(x)
    n = len(y)
    return y[n // 2] if n % 2 else (y[n // 2 - 1] + y[n // 2]) / 2.0


def _skew(x, mu=None, sigma=None):
    if mu is None: mu = _mean(x)
    if sigma is None: sigma = _std(x, mu)
    if sigma == 0: return 0.0
    s = 0.0
    for v in x: d = (v - mu) / sigma; s += d * d * d
    return s / len(x)


def _kurtosis(x, mu=None, sigma=None):
    if mu is None: mu = _mean(x)
    if sigma is None: sigma = _std(x, mu)
    if sigma == 0: return 0.0
    s = 0.0
    for v in x: d = (v - mu) / sigma; s += d * d * d * d
    return s / len(x) - 3.0


def _iqr(x):
    y = sorted(x); n = len(y)
    return y[3 * n // 4] - y[n // 4]


def _zcr(x):
    c = 0
    for i in range(1, len(x)):
        if (x[i] >= 0) != (x[i - 1] >= 0): c += 1
    return c / (len(x) - 1) if len(x) > 1 else 0.0


def _acorr1(x, mu=None):
    if mu is None: mu = _mean(x)
    n = len(x); num = 0.0; den = 0.0
    for i in range(n - 1): num += (x[i] - mu) * (x[i + 1] - mu)
    for i in range(n): den += (x[i] - mu) * (x[i] - mu)
    return num / den if den != 0 else 0.0


def time_features(signal):
    """14 time-domain features from a 1D signal."""
    n = len(signal)
    if n == 0: return [0.0] * 14
    mu = _mean(signal)
    sigma = _std(signal, mu)
    var = sigma * sigma
    rms = math.sqrt(sum(v * v for v in signal) / n)
    mx = max(signal); mn = min(signal)
    ptp = mx - mn
    med = _median(signal)
    sk = _skew(signal, mu, sigma)
    ku = _kurtosis(signal, mu, sigma)
    ir = _iqr(signal)
    sma = sum(abs(v) for v in signal) / n
    zc = _zcr(signal)
    ac = _acorr1(signal, mu)
    return [mu, sigma, var, rms, ptp, mx, mn, med, sk, ku, ir, sma, zc, ac]


def extract_features(window):
    """Extract 184 non-FFT features from (128, 9) window.

    Feature groups (matching FEATURE_NAMES order from model_params.py):
      0-13:   14 time × ax
      14-27:  14 time × ay
      28-41:  14 time × az
      42-55:  14 time × gx
      56-69:  14 time × gy
      70-83:  14 time × gz
      84-97:  14 time × mx
      98-111: 14 time × my
      112-125: 14 time × mz
      126-139: 14 time × acc_mag
      140-153: 14 time × gyro_mag
      154-167: 14 time × mag_mag
      168-176: 9 cross-axis correlations
      177-179: 3 jerk_mag stats
      180: acc_vertical_ratio
      181: gyro_pitch_ratio
      182: mag_heading_std
      183: acc_gyro_corr
    """
    fs = []  # all 184 features

    # ── 9 axes time features (126) ──
    for ch in range(9):
        sig = [window[i][ch] for i in range(128)]
        fs.extend(time_features(sig))

    # ── Magnitude signals ──
    acc_mag = [math.sqrt(w[0]**2 + w[1]**2 + w[2]**2) for w in window]
    gyro_mag = [math.sqrt(w[3]**2 + w[4]**2 + w[5]**2) for w in window]
    mag_mag = [math.sqrt(w[6]**2 + w[7]**2 + w[8]**2) for w in window]

    # ── Magnitude time features (42) ──
    fs.extend(time_features(acc_mag))
    fs.extend(time_features(gyro_mag))
    fs.extend(time_features(mag_mag))

    # ── Cross-axis correlations (9) ──
    def pearson(x, y):
        n = len(x); mx = _mean(x); my = _mean(y)
        sx = _std(x, mx); sy = _std(y, my)
        if sx == 0 or sy == 0: return 0.0
        cov = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / n
        return cov / (sx * sy)

    for a, b in [(0, 1), (0, 2), (1, 2)]:  # acc correlations
        fs.append(pearson([w[a] for w in window], [w[b] for w in window]))
    for a, b in [(3, 4), (3, 5), (4, 5)]:  # gyro correlations
        fs.append(pearson([w[a] for w in window], [w[b] for w in window]))
    for a, b in [(6, 7), (6, 8), (7, 8)]:  # mag correlations
        fs.append(pearson([w[a] for w in window], [w[b] for w in window]))

    # ── jerk_mag stats (3) ──
    jerk = [0.0]
    for i in range(1, 128):
        jerk.append(acc_mag[i] - acc_mag[i - 1])
    fs.append(_mean(jerk))
    fs.append(_std(jerk, _mean(jerk)))
    fs.append(max(jerk))

    # ── acc_vertical_ratio (1) ──
    az_sig = [w[2] for w in window]
    az_var = _std(az_sig)**2
    ax_ay_var = _std([w[0] for w in window])**2 + _std([w[1] for w in window])**2
    total_var = az_var + ax_ay_var
    fs.append(az_var / total_var if total_var > 0 else 0.5)

    # ── gyro_pitch_ratio (1) ──
    gx_var = _std([w[3] for w in window])**2
    gy_var = _std([w[4] for w in window])**2
    gz_var = _std([w[5] for w in window])**2
    total_g = gx_var + gy_var + gz_var
    fs.append(gy_var / total_g if total_g > 0 else 1.0 / 3.0)

    # ── mag_heading_std (1) ──
    headings = []
    for w in window:
        h = math.atan2(w[7], w[6])  # heading = atan2(my, mx)
        headings.append(h)
    fs.append(_std(headings))

    # ── acc_gyro_corr (1) ──
    fs.append(pearson(acc_mag, gyro_mag))

    return fs


# ══════════════════════════════════════════════════════════════════════
# Classifier
# ══════════════════════════════════════════════════════════════════════

def predict(features):
    """Standardize → linear(W·x+b) → softmax → argmax."""
    # Standardize
    x = [0.0] * N_FEATURES
    for i in range(N_FEATURES):
        if SCALER_STD[i] != 0:
            x[i] = (features[i] - SCALER_MEAN[i]) / SCALER_STD[i]

    # Linear: logits = x @ W^T + b
    logits = [0.0] * N_CLASSES
    for c in range(N_CLASSES):
        s = INTERCEPT[c]
        row = COEF[c]
        for i in range(N_FEATURES):
            s += x[i] * row[i]
        logits[c] = s

    # Softmax
    mx = max(logits)
    exp_sum = 0.0
    exps = [0.0] * N_CLASSES
    for c in range(N_CLASSES):
        e = math.exp(logits[c] - mx)
        exps[c] = e
        exp_sum += e
    probs = [e / exp_sum if exp_sum > 0 else 1.0 / N_CLASSES for e in exps]

    # Argmax
    best_c, best_p = 0, probs[0]
    for c in range(1, N_CLASSES):
        if probs[c] > best_p:
            best_c, best_p = c, probs[c]

    return best_c, best_p, ACTIVITIES.get(best_c, "unknown")


# ══════════════════════════════════════════════════════════════════════
# LED display
# ══════════════════════════════════════════════════════════════════════

LED_COLORS = {
    0: (0, 0, 255),        # sit → Blue
    1: (0, 255, 255),      # stand → Cyan
    2: (0, 255, 0),        # walk → Green
    3: (255, 255, 0),      # run → Yellow
    4: (255, 165, 0),      # upstairs → Orange
    5: (128, 0, 255),      # downstairs → Purple
    6: (255, 0, 0),        # fall → Red
}


def show_result(class_id, confidence):
    color = LED_COLORS.get(class_id, (255, 255, 255))
    if class_id == 6:
        for _ in range(3):
            np[0] = color; np.write(); sleep_ms(150)
            np[0] = (0, 0, 0); np.write(); sleep_ms(150)
    else:
        r = int(color[0] * min(confidence, 1.0))
        g = int(color[1] * min(confidence, 1.0))
        b = int(color[2] * min(confidence, 1.0))
        np[0] = (r, g, b); np.write()


# ══════════════════════════════════════════════════════════════════════
# Init & Main loop
# ══════════════════════════════════════════════════════════════════════

WINDOW_SIZE = 128
STRIDE = 64
INTERVAL_MS = 20


def init_sensors():
    for _ in range(3):
        try:
            i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')
            sleep_ms(100)
            i2c.writeto_mem(MPU_ADDR, 0x1C, b'\x10')
            i2c.writeto_mem(MPU_ADDR, 0x1B, b'\x18')
            i2c.readfrom_mem(MPU_ADDR, 0x3B, 14)
            print("MPU6050 OK")
            break
        except Exception as e:
            print(f"MPU retry {_+1}: {e}")
            sleep_ms(500)

    for _ in range(3):
        try:
            i2c.writeto_mem(HMC_ADDR, 0x02, b'\x00')
            sleep_ms(50)
            i2c.readfrom_mem(HMC_ADDR, 0x03, 6)
            print("HMC5883L OK")
            break
        except Exception as e:
            print(f"HMC retry {_+1}: {e}")
            sleep_ms(500)


def main():
    print("=" * 40)
    print("HAR Real-time Inference")
    print(f"Features: {N_FEATURES}, Classes: {N_CLASSES}")
    print("=" * 40)

    try:
        init_sensors()
    except Exception as e:
        print(f"Init failed: {e}")
        for _ in range(10):
            np[0] = (255, 0, 0); np.write(); sleep_ms(200)
            np[0] = (0, 0, 0); np.write(); sleep_ms(200)
        return

    # Ready signal
    for _ in range(3):
        np[0] = (40, 40, 40); np.write(); sleep_ms(250)
        np[0] = (0, 0, 0); np.write(); sleep_ms(250)

    print("READY. Perform activities...")
    for cid in range(N_CLASSES):
        c = LED_COLORS.get(cid, (255, 255, 255))
        print(f"  {ACTIVITIES[cid]:12s} → LED ({c[0]},{c[1]},{c[2]})")

    buffer = [(0.0,) * 9] * WINDOW_SIZE
    buf_idx = 0
    samples = 0
    next_infer = STRIDE
    last_t = ticks_ms()

    while True:
        try:
            sample = read_9ch()
        except Exception as e:
            print(f"Read err: {e}")
            sleep_ms(10)
            continue

        buffer[buf_idx] = sample
        buf_idx = (buf_idx + 1) % WINDOW_SIZE
        samples += 1

        if samples >= next_infer:
            next_infer += STRIDE

            window = []
            for i in range(WINDOW_SIZE):
                window.append(buffer[(buf_idx - WINDOW_SIZE + i) % WINDOW_SIZE])

            try:
                feats = extract_features(window)
                cid, conf, name = predict(feats)
                show_result(cid, conf)
                t = samples / 50.0
                mark = " *** FALL ***" if cid == 6 else ""
                print(f"[{t:5.1f}s] {name:12s} conf={conf:.3f}{mark}")
            except Exception as e:
                print(f"Infer err: {e}")

        elapsed = ticks_diff(ticks_ms(), last_t)
        wait = INTERVAL_MS - elapsed
        if wait > 0:
            sleep_ms(wait)
        last_t = ticks_ms()


if __name__ == "__main__":
    main()
