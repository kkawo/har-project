"""Quick test: read all raw lines from ESP32 serial."""
import serial
import serial.tools.list_ports
import time

# Find ESP32
port = None
for p in serial.tools.list_ports.comports():
    if any(k in p.description for k in ["CP210", "CH340", "Silicon Labs", "ESP32", "USB Serial"]):
        port = p.device
        break
if not port:
    ports = list(serial.tools.list_ports.comports())
    port = ports[0].device if ports else None

if not port:
    print("No serial port found!")
    exit()

print(f"Opening {port} at 115200...")
ser = serial.Serial(port, 115200, timeout=1)
# Don't reset ESP32
ser.dtr = False
ser.rts = False
time.sleep(1)

print("Reading... (Ctrl+C to stop)\n")
buffer = ""
while True:
    try:
        n = ser.in_waiting or 1
        chunk = ser.read(n).decode("utf-8", errors="replace")
        if chunk:
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if line:
                    if line.startswith("DATA:"):
                        print(f"★ {line}")
                    elif "conf=" in line:
                        print(f"  {line}")
                    else:
                        print(f"  {line}")
    except KeyboardInterrupt:
        break
    except Exception as e:
        print(f"ERR: {e}")
        time.sleep(1)

ser.close()
print("Done.")
