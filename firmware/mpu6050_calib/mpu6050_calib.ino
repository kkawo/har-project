/*
 * GY-521 (MPU6050) calibration firmware — ESP32-S3
 * Six-position accel + static gyro bias @ 50 Hz, Serial CSV output.
 *
 * Wiring:  SDA=IO17, SCL=IO18, VCC=3V3, GND=GND
 * Commands via Serial @ 115200 baud:
 *   START  — begin streaming
 *   STOP   — stop streaming
 *   MARK <label>  — mark position (e.g. "MARK +Z_down")
 *   ?      — print status
 *
 * Output CSV: sample,ax,ay,az,gx,gy,gz,label
 *   ax/ay/az in m/s^2 (raw, uncalibrated, +/-8g range)
 *   gx/gy/gz in deg/s (raw, uncalibrated, +/-2000 deg/s range)
 */

#include <Wire.h>

#define I2C_SDA  17
#define I2C_SCL  18
#define MPU6050_ADDR  0x68

#define MPU_PWR_MGMT1   0x6B
#define MPU_ACCEL_XOUT  0x3B
#define MPU_GYRO_XOUT   0x43
#define MPU_ACCEL_CONFIG 0x1C
#define MPU_GYRO_CONFIG  0x1B
#define MPU_SMPLRT_DIV   0x19
#define MPU_CONFIG       0x1A

#define SAMPLE_INTERVAL_US 20000  // 50 Hz

volatile bool streaming = false;
unsigned long last_sample_us = 0;
unsigned long sample_count = 0;
String current_label = "";  // mark label for this position

void setup() {
  Serial.begin(115200);
  delay(300);

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000);

  Serial.println("# MPU6050 Calibration Firmware v1.0");
  Serial.println("# Commands: START, STOP, MARK <name>, ?");

  // Wake up MPU6050
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU_PWR_MGMT1);
  Wire.write(0x00);
  if (Wire.endTransmission() != 0) {
    Serial.println("# ERROR: MPU6050 not found at 0x68. Check wiring.");
    while (1) delay(1000);
  }
  delay(50);

  // Sample rate divider: 1kHz / (1+N) → N=19 gives 50 Hz
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU_SMPLRT_DIV);
  Wire.write(19);
  Wire.endTransmission();

  // DLPF: 5 Hz bandwidth
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU_CONFIG);
  Wire.write(0x06);
  Wire.endTransmission();

  // Accel: +/-8g (4096 LSB/g)
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU_ACCEL_CONFIG);
  Wire.write(0x10);
  Wire.endTransmission();

  // Gyro: +/-2000 deg/s (16.4 LSB/deg/s)
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU_GYRO_CONFIG);
  Wire.write(0x18);
  Wire.endTransmission();

  Serial.println("# MPU6050 OK. Ready.");
}

void loop() {
  handle_serial();

  if (streaming) {
    unsigned long now = micros();
    if (now - last_sample_us >= SAMPLE_INTERVAL_US) {
      last_sample_us = now;
      read_and_print();
      sample_count++;
    }
  }
}

void handle_serial() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();

  if (cmd == "START") {
    streaming = true;
    last_sample_us = micros();
    sample_count = 0;
    Serial.print("# START ");
    Serial.println(current_label);
  }
  else if (cmd == "STOP") {
    streaming = false;
    Serial.print("# STOP  samples=");
    Serial.println(sample_count);
  }
  else if (cmd.startsWith("MARK ")) {
    current_label = cmd.substring(5);
    Serial.print("# MARKED ");
    Serial.println(current_label);
  }
  else if (cmd == "?") {
    Serial.println("# MPU6050 @ 0x68, +/-8g, +/-2000dps, 50Hz");
    Serial.print("# Current label: "); Serial.println(current_label);
    Serial.print("# Streaming: "); Serial.println(streaming ? "ON" : "OFF");
    Serial.print("# Samples: "); Serial.println(sample_count);
  }
}

void read_and_print() {
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU_ACCEL_XOUT);
  Wire.endTransmission(false);
  Wire.requestFrom(MPU6050_ADDR, (uint8_t)14);

  int16_t ax_raw = Wire.read() << 8 | Wire.read();
  int16_t ay_raw = Wire.read() << 8 | Wire.read();
  int16_t az_raw = Wire.read() << 8 | Wire.read();
  Wire.read(); Wire.read(); // skip temperature
  int16_t gx_raw = Wire.read() << 8 | Wire.read();
  int16_t gy_raw = Wire.read() << 8 | Wire.read();
  int16_t gz_raw = Wire.read() << 8 | Wire.read();

  // Convert: +/-8g @ 4096 LSB/g → m/s^2
  float ax = ax_raw / 4096.0 * 9.80665;
  float ay = ay_raw / 4096.0 * 9.80665;
  float az = az_raw / 4096.0 * 9.80665;

  // Convert: +/-2000dps @ 16.4 LSB/dps
  float gx = gx_raw / 16.4;
  float gy = gy_raw / 16.4;
  float gz = gz_raw / 16.4;

  Serial.print(sample_count);
  Serial.print(",");
  Serial.print(ax, 5); Serial.print(",");
  Serial.print(ay, 5); Serial.print(",");
  Serial.print(az, 5); Serial.print(",");
  Serial.print(gx, 4); Serial.print(",");
  Serial.print(gy, 4); Serial.print(",");
  Serial.print(gz, 4); Serial.print(",");
  Serial.println(current_label);
}
