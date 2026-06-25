"""
HAR Real-time Inference Firmware for ESP32-S3.

Reads MPU6050 + HMC5883L @ 50Hz into a circular buffer.
Every 1.28s (64 new samples, 50% overlap), extracts 14 time-domain
features per axis (126-dim), applies calibration + standardization,
runs a linear classifier, and shows the result on NeoPixel LED + serial.

Setup:
  1. Copy main.py + model_params.py to ESP32 root (via Thonny/mpremote)
  2. Power on, wait for LED calibration flash
  3. Wear on waist, perform activities
  4. Watch LED color change to indicate recognized activity

LED color map:
  sit       → Blue
  stand     → Cyan
  walk      → Green
  run       → Yellow
  upstairs  → Orange
  downstairs → Purple
  fall      → Red (blink)
  unknown   → White
"""

from machine import Pin, SoftI2C
from time import sleep_ms, sleep_us, ticks_ms, ticks_diff
import neopixel
import struct
import math

# ─── Hardware ───────────────────────────────────────────────────────
SDA = Pin(17)
SCL = Pin(18)
i2c = SoftI2C(sda=SDA, scl=SCL, freq=400000)
np = neopixel.NeoPixel(Pin(48), 1)

MPU_ADDR = 0x68
HMC_ADDR = 0x1E
ACCL_SENS = 4096.0    # ±8g → 4096 LSB/g
GYRO_SENS = 16.4      # ±2000dps → 16.4 LSB/(°/s)
GRAVITY = 9.80665

# ─── Import model parameters ────────────────────────────────────────
from model_params import (
    N_CLASSES, N_FEATURES, ACTIVITIES, COEF, INTERCEPT,
    SCALER_MEAN, SCALER_STD, ACC_BIAS, ACC_SCALE,
)


# ══════════════════════════════════════════════════════════════════════
# Sensor I/O
# ══════════════════════════════════════════════════════════════════════

def mpu_read():
    """Read 6-axis from MPU6050. Returns (ax, ay, az, gx, gy, gz) in m/s² and °/s."""
    data = i2c.readfrom_mem(MPU_ADDR, 0x3B, 14)
    ax = struct.unpack(">h", data[0:2])[0] / ACCL_SENS * GRAVITY
    ay = struct.unpack(">h", data[2:4])[0] / ACCL_SENS * GRAVITY
    az = struct.unpack(">h", data[4:6])[0] / ACCL_SENS * GRAVITY
    gx = struct.unpack(">h", data[8:10])[0] / GYRO_SENS
    gy = struct.unpack(">h", data[10:12])[0] / GYRO_SENS
    gz = struct.unpack(">h", data[12:14])[0] / GYRO_SENS
    return ax, ay, az, gx, gy, gz


def hmc_read():
    """Read 3-axis from HMC5883L. Returns (mx, my, mz) in uT.
    HMC5883L register order: X, Z, Y (non-standard!).
    """
    data = i2c.readfrom_mem(HMC_ADDR, 0x03, 6)
    mx = struct.unpack(">h", data[0:2])[0]
    mz = struct.unpack(">h", data[2:4])[0]  # swapped!
    my = struct.unpack(">h", data[4:6])[0]
    # HMC5883L sensitivity: 1090 LSB/Gauss, 1 Gauss = 100 uT → 0.92 uT/LSB
    sens = 1090.0 / 100.0
    return mx / sens, my / sens, mz / sens


def read_9ch():
    """Read all 9 channels and apply accelerometer calibration."""
    ax, ay, az, gx, gy, gz = mpu_read()
    mx, my, mz = hmc_read()
    # Apply accelerometer calibration
    ax = (ax - ACC_BIAS[0]) * ACC_SCALE[0]
    ay = (ay - ACC_BIAS[1]) * ACC_SCALE[1]
    az = (az - ACC_BIAS[2]) * ACC_SCALE[2]
    return ax, ay, az, gx, gy, gz, mx, my, mz


# ══════════════════════════════════════════════════════════════════════
# Feature extraction — pure Python, no numpy
# ══════════════════════════════════════════════════════════════════════

def _mean(x):
    s = 0.0
    for v in x:
        s += v
    return s / len(x)


def _std(x, mean=None):
    if mean is None:
        mean = _mean(x)
    s = 0.0
    for v in x:
        d = v - mean
        s += d * d
    return math.sqrt(s / len(x))


def _median(x):
    y = sorted(x)
    n = len(y)
    if n % 2:
        return y[n // 2]
    return (y[n // 2 - 1] + y[n // 2]) / 2.0


def _skew(x, mean=None, std=None):
    if mean is None:
        mean = _mean(x)
    if std is None:
        std = _std(x, mean)
    if std == 0:
        return 0.0
    n = len(x)
    s = 0.0
    for v in x:
        d = (v - mean) / std
        s += d * d * d
    return s / n


def _kurtosis(x, mean=None, std=None):
    if mean is None:
        mean = _mean(x)
    if std is None:
        std = _std(x, mean)
    if std == 0:
        return 0.0
    n = len(x)
    s = 0.0
    for v in x:
        d = (v - mean) / std
        s += d * d * d * d
    return s / n - 3.0


def _iqr(x):
    y = sorted(x)
    n = len(y)
    q1 = y[n // 4]
    q3 = y[3 * n // 4]
    return q3 - q1


def _zero_cross_rate(x):
    n = len(x)
    if n < 2:
        return 0.0
    count = 0
    for i in range(1, n):
        if (x[i] >= 0) != (x[i - 1] >= 0):
            count += 1
    return count / (n - 1)


def _autocorr_lag1(x, mean=None):
    if mean is None:
        mean = _mean(x)
    n = len(x)
    num = 0.0
    den = 0.0
    for i in range(n - 1):
        num += (x[i] - mean) * (x[i + 1] - mean)
    for i in range(n):
        den += (x[i] - mean) * (x[i] - mean)
    if den == 0:
        return 0.0
    return num / den


def extract_time_features(signal):
    """Extract 14 time-domain features from a 1D signal (list of 128 floats).

    Returns list of 14 floats:
    [mean, std, var, rms, ptp, max, min, median, skew, kurtosis, iqr, sma, zcr, acorr_lag1]
    """
    n = len(signal)
    if n == 0:
        return [0.0] * 14

    mu = _mean(signal)
    sigma = _std(signal, mu)
    var = sigma * sigma

    rms = 0.0
    sma = 0.0
    mx = signal[0]
    mn = signal[0]
    for v in signal:
        rms += v * v
        sma += abs(v)
        if v > mx:
            mx = v
        if v < mn:
            mn = v
    rms = math.sqrt(rms / n)
    sma /= n

    ptp = mx - mn
    med = _median(signal)
    sk = _skew(signal, mu, sigma)
    ku = _kurtosis(signal, mu, sigma)
    ir = _iqr(signal)
    zcr = _zero_cross_rate(signal)
    ac1 = _autocorr_lag1(signal, mu)

    return [mu, sigma, var, rms, ptp, mx, mn, med, sk, ku, ir, sma, zcr, ac1]


def extract_window_features(window):
    """Extract 126 features from a (128, 9) window.

    window: list of 128 lists, each with 9 channel values.
    Returns list of 126 floats.
    """
    features = []
    for ch in range(9):
        signal = [window[i][ch] for i in range(128)]
        features.extend(extract_time_features(signal))
    return features


# ══════════════════════════════════════════════════════════════════════
# Linear classifier inference
# ══════════════════════════════════════════════════════════════════════

def softmax(logits):
    """Compute softmax probabilities. Returns list of floats."""
    # Find max for numerical stability
    mx = logits[0]
    for v in logits:
        if v > mx:
            mx = v
    exp_sum = 0.0
    exps = []
    for v in logits:
        e = math.exp(v - mx)
        exps.append(e)
        exp_sum += e
    if exp_sum == 0:
        return [1.0 / len(logits)] * len(logits)
    return [e / exp_sum for e in exps]


def predict(features):
    """Standardize → linear classify → softmax → argmax.

    Returns (class_id, confidence, class_name).
    """
    # Standardize
    x = []
    for i in range(N_FEATURES):
        if SCALER_STD[i] != 0:
            x.append((features[i] - SCALER_MEAN[i]) / SCALER_STD[i])
        else:
            x.append(0.0)

    # Linear model: logits = x @ W^T + b
    logits = [0.0] * N_CLASSES
    for c in range(N_CLASSES):
        s = INTERCEPT[c]
        for i in range(N_FEATURES):
            s += x[i] * COEF[c][i]
        logits[c] = s

    probs = softmax(logits)

    # Argmax
    best_c = 0
    best_p = probs[0]
    for c in range(1, N_CLASSES):
        if probs[c] > best_p:
            best_c = c
            best_p = probs[c]

    return best_c, best_p, ACTIVITIES.get(best_c, "unknown")


# ══════════════════════════════════════════════════════════════════════
# LED display
# ══════════════════════════════════════════════════════════════════════

LED_COLORS = {
    0: (0, 0, 255),       # sit → Blue
    1: (0, 255, 255),     # stand → Cyan
    2: (0, 255, 0),       # walk → Green
    3: (255, 255, 0),     # run → Yellow
    4: (255, 165, 0),     # upstairs → Orange
    5: (128, 0, 255),     # downstairs → Purple
    6: (255, 0, 0),       # fall → Red
}


def show_result(class_id, confidence):
    """Show activity on NeoPixel LED."""
    color = LED_COLORS.get(class_id, (255, 255, 255))
    if class_id == 6:  # fall: blink red
        np[0] = color
        np.write()
        sleep_ms(200)
        np[0] = (0, 0, 0)
        np.write()
        sleep_ms(200)
        np[0] = color
        np.write()
    else:
        # Brightness proportional to confidence
        r = int(color[0] * min(confidence, 1.0))
        gr = int(color[1] * min(confidence, 1.0))
        b = int(color[2] * min(confidence, 1.0))
        np[0] = (r, gr, b)
        np.write()


def led_ready():
    """White pulse to indicate ready."""
    for _ in range(3):
        np[0] = (50, 50, 50)
        np.write()
        sleep_ms(200)
        np[0] = (0, 0, 0)
        np.write()
        sleep_ms(200)


def led_error():
    """Red flash for error."""
    for _ in range(5):
        np[0] = (255, 0, 0)
        np.write()
        sleep_ms(100)
        np[0] = (0, 0, 0)
        np.write()
        sleep_ms(100)


# ══════════════════════════════════════════════════════════════════════
# I²C init with retry
# ══════════════════════════════════════════════════════════════════════

def init_sensors():
    """Initialize MPU6050 and HMC5883L with retry."""
    # Wake MPU6050
    for attempt in range(3):
        try:
            i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')  # Wake up
            sleep_ms(100)
            # Configure accelerometer: ±8g
            i2c.writeto_mem(MPU_ADDR, 0x1C, b'\x10')
            # Configure gyroscope: ±2000dps
            i2c.writeto_mem(MPU_ADDR, 0x1B, b'\x18')

            # Test read
            i2c.readfrom_mem(MPU_ADDR, 0x3B, 14)
            print("MPU6050 OK @ 0x68")
            break
        except Exception as e:
            print(f"MPU init attempt {attempt + 1} failed: {e}")
            sleep_ms(500)
    else:
        raise RuntimeError("MPU6050 init failed")

    # Init HMC5883L
    for attempt in range(3):
        try:
            i2c.writeto_mem(HMC_ADDR, 0x02, b'\x00')  # Continuous mode
            sleep_ms(50)
            i2c.readfrom_mem(HMC_ADDR, 0x03, 6)
            print("HMC5883L OK @ 0x1E")
            break
        except Exception as e:
            print(f"HMC init attempt {attempt + 1} failed: {e}")
            sleep_ms(500)
    else:
        raise RuntimeError("HMC5883L init failed")


# ══════════════════════════════════════════════════════════════════════
# Main loop
# ══════════════════════════════════════════════════════════════════════

WINDOW_SIZE = 128    # 2.56s @ 50Hz
STRIDE = 64          # 1.28s → 50% overlap
SAMPLE_INTERVAL_MS = 20  # 50Hz


def main():
    print("=" * 40)
    print("HAR Real-time Inference")
    print(f"Model: {N_CLASSES} classes, {N_FEATURES} features")
    print(f"Window: {WINDOW_SIZE} samples, stride: {STRIDE}")
    print("=" * 40)

    # Init hardware
    try:
        init_sensors()
    except RuntimeError as e:
        print(f"Sensor init failed: {e}")
        led_error()
        return

    led_ready()
    print("Ready! Perform activities...")
    print("Activity LED color map:")
    for cid in range(N_CLASSES):
        print(f"  {ACTIVITIES[cid]:12s} → {LED_COLORS.get(cid)}")

    # Circular buffer: list of 9-tuples
    buffer = [(0.0,) * 9] * WINDOW_SIZE
    buf_idx = 0
    samples_collected = 0
    next_inference = STRIDE

    last_time = ticks_ms()

    while True:
        # ── Read sensors ──
        try:
            sample = read_9ch()
        except Exception as e:
            print(f"Sensor read error: {e}")
            sleep_ms(10)
            continue

        # ── Store in circular buffer ──
        buffer[buf_idx] = sample
        buf_idx = (buf_idx + 1) % WINDOW_SIZE
        samples_collected += 1

        # ── Inference trigger every STRIDE samples ──
        if samples_collected >= next_inference:
            next_inference += STRIDE

            # Build window from circular buffer
            window = []
            for i in range(WINDOW_SIZE):
                idx = (buf_idx - WINDOW_SIZE + i) % WINDOW_SIZE
                window.append(buffer[idx])

            # Extract features
            try:
                features = extract_window_features(window)
            except Exception as e:
                print(f"Feature extraction error: {e}")
                continue

            # Predict
            try:
                class_id, conf, name = predict(features)
            except Exception as e:
                print(f"Inference error: {e}")
                continue

            # Display
            show_result(class_id, conf)
            t = samples_collected / 50  # seconds elapsed
            marker = " *** FALL ***" if class_id == 6 else ""
            print(f"[{t:5.1f}s] {name:12s} | conf={conf:.3f}{marker}")

        # ── Maintain 50Hz timing ──
        elapsed = ticks_diff(ticks_ms(), last_time)
        wait_ms = SAMPLE_INTERVAL_MS - elapsed
        if wait_ms > 0:
            sleep_ms(wait_ms)
        last_time = ticks_ms()


# ── Run ──
if __name__ == "__main__":
    main()
