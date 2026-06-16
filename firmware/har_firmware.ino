/*
 * HAR Project — ESP32-S3 Sensor Data Acquisition Firmware
 * MPU6050 (0x68) + HMC5883L (0x1E) @ 50 Hz via I2C
 * SDA=IO17, SCL=IO18, 3V3 power
 *
 * Usage:
 *   1. Select board: ESP32S3 Dev Module
 *   2. Install libraries: Adafruit MPU6050, Adafruit HMC5883L (or use raw I2C)
 *   3. Serial Monitor @ 115200 baud
 *   4. Output: CSV stream — timestamp,ax,ay,az,gx,gy,gz,mx,my,mz
 *
 * Commands (send via Serial):
 *   START   — begin streaming data
 *   STOP    — stop streaming
 *   CALIB   — print calibration raw data header
 *   ?       — print device status
 */

#include <Wire.h>

// ─── Pin Definitions ─────────────────────────────────────────────────
#define I2C_SDA  17
#define I2C_SCL  18
#define LED_PIN  13  // Optional: onboard LED for status

// ─── I2C Addresses ────────────────────────────────────────────────────
#define MPU6050_ADDR  0x68
#define HMC5883L_ADDR 0x1E

// ─── MPU6050 Registers ────────────────────────────────────────────────
#define MPU_PWR_MGMT1   0x6B
#define MPU_ACCEL_XOUT  0x3B
#define MPU_GYRO_XOUT   0x43
#define MPU_ACCEL_CONFIG 0x1C
#define MPU_GYRO_CONFIG  0x1B
#define MPU_SMPLRT_DIV   0x19
#define MPU_CONFIG       0x1A

// ─── HMC5883L Registers ───────────────────────────────────────────────
#define HMC_CONFIG_A     0x00
#define HMC_CONFIG_B     0x01
#define HMC_MODE         0x02
#define HMC_DATA_X       0x03

// ─── Timing ───────────────────────────────────────────────────────────
#define SAMPLE_INTERVAL_US 20000  // 50 Hz = 20000 µs

// ─── Global State ─────────────────────────────────────────────────────
volatile bool streaming = false;
unsigned long last_sample_us = 0;
unsigned long sample_count = 0;

// Calibration data (loaded from calib_params.json equivalent)
float accel_bias[3] = {0, 0, 0};
float accel_scale[3] = {1, 1, 1};
float mag_hard_iron[3] = {0, 0, 0};

// ─── Setup ────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000);  // 400 kHz Fast I2C

  Serial.println("# HAR ESP32-S3 Firmware v1.0");
  Serial.println("# MPU6050 + HMC5883L @ 50 Hz");
  Serial.println("# ---");

  if (!mpu6050_init()) {
    Serial.println("# ERROR: MPU6050 init failed! Check wiring.");
    while (1) {
      digitalWrite(LED_PIN, !digitalRead(LED_PIN));
      delay(200);
    }
  }
  Serial.println("# MPU6050 OK (0x68)");

  if (!hmc5883l_init()) {
    Serial.println("# WARNING: HMC5883L init failed. Mag data will be zero.");
  } else {
    Serial.println("# HMC5883L OK (0x1E)");
  }

  Serial.println("# Ready. Commands: START, STOP, CALIB, ?");
  Serial.println("# Columns: sample, ax, ay, az, gx, gy, gz, mx, my, mz");
  digitalWrite(LED_PIN, HIGH);
}

// ─── Main Loop — Non-blocking 50 Hz sampler ───────────────────────────
void loop() {
  handle_serial();

  if (streaming) {
    unsigned long now = micros();
    if (now - last_sample_us >= SAMPLE_INTERVAL_US) {
      last_sample_us = now;
      read_and_print_sensors();
      sample_count++;
    }
  }
}

// ─── Serial Command Handler ───────────────────────────────────────────
void handle_serial() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "START") {
    streaming = true;
    last_sample_us = micros();
    sample_count = 0;
    Serial.println("# Streaming started @ 50 Hz");
    digitalWrite(LED_PIN, HIGH);
  }
  else if (cmd == "STOP") {
    streaming = false;
    Serial.print("# Streaming stopped. Samples: ");
    Serial.println(sample_count);
    digitalWrite(LED_PIN, LOW);
  }
  else if (cmd == "CALIB") {
    Serial.println("# Calibration mode — place sensor in position, send START");
    Serial.println("# Six positions: +Z_down, -Z_up, +X_down, -X_up, +Y_down, -Y_up");
    Serial.println("# Collect ≥100 samples per position");
  }
  else if (cmd == "?") {
    print_status();
  }
}

// ─── Sensor Read ──────────────────────────────────────────────────────
void read_and_print_sensors() {
  int16_t ax_raw, ay_raw, az_raw, gx_raw, gy_raw, gz_raw;
  int16_t mx_raw, my_raw, mz_raw;

  // MPU6050: 14 bytes starting from ACCEL_XOUT
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU_ACCEL_XOUT);
  if (Wire.endTransmission(false) == 0) {
    Wire.requestFrom(MPU6050_ADDR, (uint8_t)14);
    ax_raw = Wire.read() << 8 | Wire.read();
    ay_raw = Wire.read() << 8 | Wire.read();
    az_raw = Wire.read() << 8 | Wire.read();
    // Skip temperature (2 bytes)
    Wire.read(); Wire.read();
    gx_raw = Wire.read() << 8 | Wire.read();
    gy_raw = Wire.read() << 8 | Wire.read();
    gz_raw = Wire.read() << 8 | Wire.read();
  } else {
    ax_raw = ay_raw = az_raw = gx_raw = gy_raw = gz_raw = 0;
  }

  // Convert — MPU6050 default: ±2g (16384 LSB/g), ±250°/s (131 LSB/°/s)
  float ax = (ax_raw / 16384.0) * 9.80665;
  float ay = (ay_raw / 16384.0) * 9.80665;
  float az = (az_raw / 16384.0) * 9.80665;
  float gx = gx_raw / 131.0;
  float gy = gy_raw / 131.0;
  float gz = gz_raw / 131.0;

  // Apply accelerometer calibration
  ax = (ax - accel_bias[0]) * accel_scale[0];
  ay = (ay - accel_bias[1]) * accel_scale[1];
  az = (az - accel_bias[2]) * accel_scale[2];

  // HMC5883L: 6 bytes starting from DATA_X
  Wire.beginTransmission(HMC5883L_ADDR);
  Wire.write(HMC_DATA_X);
  if (Wire.endTransmission(false) == 0) {
    Wire.requestFrom(HMC5883L_ADDR, (uint8_t)6);
    mx_raw = Wire.read() << 8 | Wire.read();
    mz_raw = Wire.read() << 8 | Wire.read();  // HMC5883L order: X, Z, Y
    my_raw = Wire.read() << 8 | Wire.read();
  } else {
    mx_raw = my_raw = mz_raw = 0;
  }

  // Convert — HMC5883L default: ±1.3Ga (1090 LSB/Ga → 0.92 LSB/µT)
  float mx = mx_raw * 0.92;
  float my = my_raw * 0.92;
  float mz = mz_raw * 0.92;

  // Apply magnetometer hard iron correction
  mx -= mag_hard_iron[0];
  my -= mag_hard_iron[1];
  mz -= mag_hard_iron[2];

  // Output CSV
  Serial.print(sample_count);
  Serial.print(",");
  Serial.print(ax, 4); Serial.print(",");
  Serial.print(ay, 4); Serial.print(",");
  Serial.print(az, 4); Serial.print(",");
  Serial.print(gx, 2); Serial.print(",");
  Serial.print(gy, 2); Serial.print(",");
  Serial.print(gz, 2); Serial.print(",");
  Serial.print(mx, 2); Serial.print(",");
  Serial.print(my, 2); Serial.print(",");
  Serial.println(mz, 2);
}

// ─── MPU6050 Initialization ───────────────────────────────────────────
bool mpu6050_init() {
  // Wake up
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU_PWR_MGMT1);
  Wire.write(0x00);  // Wake up, internal 8MHz oscillator
  if (Wire.endTransmission() != 0) return false;
  delay(50);

  // Sample rate divider: 50 Hz = 1000 / (1 + div) → div = 19
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU_SMPLRT_DIV);
  Wire.write(19);
  Wire.endTransmission();

  // DLPF: 5 Hz bandwidth (most stable for 50 Hz)
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU_CONFIG);
  Wire.write(0x06);  // DLPF_CFG=6 → 5 Hz BW
  Wire.endTransmission();

  // Accelerometer: ±8g
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU_ACCEL_CONFIG);
  Wire.write(0x10);  // AFS_SEL=2 → ±8g (4096 LSB/g)
  Wire.endTransmission();

  // Gyroscope: ±2000°/s
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU_GYRO_CONFIG);
  Wire.write(0x18);  // FS_SEL=3 → ±2000°/s (16.4 LSB/°/s)
  Wire.endTransmission();

  return true;
}

// ─── HMC5883L Initialization ──────────────────────────────────────────
bool hmc5883l_init() {
  // Config A: 8 samples averaged, 75 Hz ODR, normal measurement
  Wire.beginTransmission(HMC5883L_ADDR);
  Wire.write(HMC_CONFIG_A);
  Wire.write(0x78);  // MA1:MA0=11 (8 avg), DO2:DO0=110 (75 Hz)
  if (Wire.endTransmission() != 0) return false;

  // Config B: ±1.3 Ga (default gain)
  Wire.beginTransmission(HMC5883L_ADDR);
  Wire.write(HMC_CONFIG_B);
  Wire.write(0x20);  // GN2:GN0=001 → ±1.3Ga (1090 LSB/Ga)
  Wire.endTransmission();

  // Mode: continuous measurement
  Wire.beginTransmission(HMC5883L_ADDR);
  Wire.write(HMC_MODE);
  Wire.write(0x00);  // Continuous
  Wire.endTransmission();

  return true;
}

// ─── Status ────────────────────────────────────────────────────────────
void print_status() {
  Serial.println("# === Device Status ===");
  Serial.print("# I2C: SDA=IO"); Serial.print(I2C_SDA);
  Serial.print(", SCL=IO"); Serial.println(I2C_SCL);
  Serial.println("# MPU6050: 0x68, ±8g, ±2000°/s");
  Serial.println("# HMC5883L: 0x1E, ±1.3Ga");
  Serial.print("# Streaming: "); Serial.println(streaming ? "ON" : "OFF");
  Serial.print("# Sample count: "); Serial.println(sample_count);
}
