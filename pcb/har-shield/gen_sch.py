"""Generate KiCad 8 .kicad_sch — uses standard system library symbols (no embedded)."""
import uuid, os

def uid(): return str(uuid.uuid4())

sch_uuid = uid()
sheet_uuid = uid()

# ── Component data ─────────────────────────────────────────────────────
# (lib_id, reference, value, footprint, x, y, rotation, pin_count_or_list)
#
# Using KiCad 8 standard system library symbols:
#   Device:R, Device:C, Device:LED
#   Connector:Conn_01x19_Female, Conn_01x08_Female, Conn_01x05_Female

J1_cx, J1_cy = 25.4, 109.22    # ESP32 LEFT 19-pin
J2_cx, J2_cy = 171.45, 109.22   # ESP32 RIGHT 19-pin
J3_cx, J3_cy = 96.52, 129.54    # GY-521 8-pin
J4_cx, J4_cy = 96.52, 48.26     # GY-273 5-pin
R1_cx, R1_cy = 63.5, 124.46     # SCL pull-up
R2_cx, R2_cy = 63.5, 111.76     # SDA pull-up
C1_cx, C1_cy = 149.86, 134.62   # decouple GY-521
C2_cx, C2_cy = 149.86, 53.34    # decouple GY-273
D1_cx, D1_cy = 40.64, 35.56     # power LED
R3_cx, R3_cy = 40.64, 50.8      # LED resistor

components = [
    ("Connector:Conn_01x19_Female", "J1", "ESP32_LEFT",   "Connector_PinHeader_2.54mm:PinHeader_1x19_P2.54mm_Vertical", J1_cx, J1_cy, 0, 19),
    ("Connector:Conn_01x19_Female", "J2", "ESP32_RIGHT",  "Connector_PinHeader_2.54mm:PinHeader_1x19_P2.54mm_Vertical", J2_cx, J2_cy, 0, 19),
    ("Connector:Conn_01x08_Female", "J3", "GY-521_MPU6050","Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical", J3_cx, J3_cy, 0, 8),
    ("Connector:Conn_01x05_Female", "J4", "GY-273_HMC5883L","Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical", J4_cx, J4_cy, 0, 5),
    ("Device:R",                     "R1", "4.7k",         "Resistor_SMD:R_0805_2012Metric",                           R1_cx, R1_cy, 90, 2),
    ("Device:R",                     "R2", "4.7k",         "Resistor_SMD:R_0805_2012Metric",                           R2_cx, R2_cy, 90, 2),
    ("Device:C",                     "C1", "100nF",        "Capacitor_SMD:C_0805_2012Metric",                          C1_cx, C1_cy, 0, 2),
    ("Device:C",                     "C2", "100nF",        "Capacitor_SMD:C_0805_2012Metric",                          C2_cx, C2_cy, 0, 2),
    ("Device:LED",                   "D1", "LED",          "LED_SMD:LED_0805_2012Metric",                              D1_cx, D1_cy, 0, 2),
    ("Device:R",                     "R3", "220",          "Resistor_SMD:R_0805_2012Metric",                           R3_cx, R3_cy, 90, 2),
]

# ── Pin position helpers ───────────────────────────────────────────────
def conn_pin_pos(cx, cy, n, pin_i, rot=0):
    """Absolute position of pin pin_i (1-indexed) on N-pin connector."""
    i = pin_i - 1
    top = (n - 1) * 1.27
    rel_y = top - i * 2.54
    if rot == 0:   return (cx - 5.08, cy + rel_y)
    if rot == 90:  return (cx + rel_y, cy + 5.08)
    if rot == 270: return (cx - rel_y, cy - 5.08)
    return (cx + 5.08, cy - rel_y)

def res_pin_pos(cx, cy, pin, rot=0):
    if pin == 1: rx, ry = -5.08, 0
    else:        rx, ry = 5.08, 0
    if rot == 0:   return (cx + rx, cy + ry)
    if rot == 90:  return (cx - ry, cy + rx)
    if rot == 180: return (cx - rx, cy - ry)
    return (cx + ry, cy - rx)

def dev_pin_pos(cx, cy, pin, rot=0):
    """Device symbol (R, C, LED): pin 1 at (-5.08, 0), pin 2 at (+5.08, 0)."""
    return res_pin_pos(cx, cy, pin, rot)

# ── Key pin positions ──────────────────────────────────────────────────
J1_3V3 = conn_pin_pos(J1_cx, J1_cy, 19, 1, 0)
J1_GND = conn_pin_pos(J1_cx, J1_cy, 19, 15, 0)
J2_SCL = conn_pin_pos(J2_cx, J2_cy, 19, 2, 0)
J2_SDA = conn_pin_pos(J2_cx, J2_cy, 19, 5, 0)

J3_VCC = conn_pin_pos(J3_cx, J3_cy, 8, 1, 0)
J3_GND = conn_pin_pos(J3_cx, J3_cy, 8, 2, 0)
J3_SCL = conn_pin_pos(J3_cx, J3_cy, 8, 3, 0)
J3_SDA = conn_pin_pos(J3_cx, J3_cy, 8, 4, 0)
J3_AD0 = conn_pin_pos(J3_cx, J3_cy, 8, 7, 0)

J4_VCC = conn_pin_pos(J4_cx, J4_cy, 5, 1, 0)
J4_GND = conn_pin_pos(J4_cx, J4_cy, 5, 2, 0)
J4_SCL = conn_pin_pos(J4_cx, J4_cy, 5, 3, 0)
J4_SDA = conn_pin_pos(J4_cx, J4_cy, 5, 4, 0)

R1_1 = dev_pin_pos(R1_cx, R1_cy, 1, 90)
R1_2 = dev_pin_pos(R1_cx, R1_cy, 2, 90)
R2_1 = dev_pin_pos(R2_cx, R2_cy, 1, 90)
R2_2 = dev_pin_pos(R2_cx, R2_cy, 2, 90)
C1_1 = dev_pin_pos(C1_cx, C1_cy, 1, 0)
C1_2 = dev_pin_pos(C1_cx, C1_cy, 2, 0)
C2_1 = dev_pin_pos(C2_cx, C2_cy, 1, 0)
C2_2 = dev_pin_pos(C2_cx, C2_cy, 2, 0)
D1_K = dev_pin_pos(D1_cx, D1_cy, 1, 0)
D1_A = dev_pin_pos(D1_cx, D1_cy, 2, 0)
R3_1 = dev_pin_pos(R3_cx, R3_cy, 1, 90)
R3_2 = dev_pin_pos(R3_cx, R3_cy, 2, 90)

# ── Wires ──────────────────────────────────────────────────────────────
wires = []
junctions = set()

def w(x1,y1,x2,y2): wires.append((x1,y1,x2,y2))
def j(x,y): junctions.add((round(x,4), round(y,4)))
def rh(sx,sy,ex,ey):
    w(sx,sy,ex,sy); w(ex,sy,ex,ey); j(ex,sy)
def rv(sx,sy,ex,ey):
    w(sx,sy,sx,ey); w(sx,ey,ex,ey); j(sx,ey)

# +3V3 bus line (horizontal at y=25)
bus3_y = 25.0; bus3_x1, bus3_x2 = 20.0, 160.0
w(bus3_x1, bus3_y, bus3_x2, bus3_y)
for px, py in [J1_3V3, R1_1, R2_1, C1_1, C2_1, R3_1, J3_VCC, J4_VCC]:
    rh(px, py, px, bus3_y); j(px, bus3_y)

# R3_2 → D1_A
w(R3_2[0], R3_2[1], R3_2[0], D1_A[1])
w(R3_2[0], D1_A[1], D1_A[0], D1_A[1])

# GND bus line (horizontal at y=155)
bus_gnd_y = 155.0
w(20.0, bus_gnd_y, 165.0, bus_gnd_y)
for px, py in [J1_GND, J3_GND, J3_AD0, J4_GND, C1_2, C2_2, D1_K]:
    rh(px, py, px, bus_gnd_y); j(px, bus_gnd_y)

# SCL bus (horizontal at y=138)
scl_y = 138.0
w(55.0, scl_y, 110.0, scl_y)
for px, py in [R1_2, J2_SCL, J3_SCL, J4_SCL]:
    rh(px, py, px, scl_y); j(px, scl_y)

# SDA bus (horizontal at y=144)
sda_y = 144.0
w(55.0, sda_y, 110.0, sda_y)
for px, py in [R2_2, J2_SDA, J3_SDA, J4_SDA]:
    rh(px, py, px, sda_y); j(px, sda_y)

# ── Output ─────────────────────────────────────────────────────────────
symbol_lines = []
for lib_id, ref, val, fp, cx, cy, rot, npins in components:
    pins_str = "\n".join(f'      (pin "{p}" (uuid "{uid()}"))' for p in range(1, npins + 1))
    # Place Reference above, Value below
    symbol_lines.append(f"""(symbol
      (lib_id "{lib_id}")
      (at {cx:.2f} {cy:.2f} {rot})
      (uuid "{uid()}")
      (property "Reference" "{ref}" (at {cx:.2f} {cy - 6.35:.2f} 0) (id 0))
      (property "Value" "{val}" (at {cx:.2f} {cy + 6.35:.2f} 0) (id 1))
      (property "Footprint" "{fp}" (at {cx:.2f} {cy:.2f} 0) (id 2))
      (property "Datasheet" "" (at {cx:.2f} {cy:.2f} 0) (id 3))
{pins_str}
    )""")

wire_lines   = [f'  (wire (pts (xy {x1:.2f} {y1:.2f}) (xy {x2:.2f} {y2:.2f})) (stroke (width 0.1524) (type default)) (uuid "{uid()}"))' for x1,y1,x2,y2 in wires]
junc_lines   = [f'  (junction (at {x:.2f} {y:.2f}) (diameter 1.016) (color 0 0 0 0) (uuid "{uid()}"))' for x,y in sorted(junctions)]

content = f"""(kicad_sch
  (version 20231120)
  (generator "eeschema")
  (generator_version "8.0")
  (uuid "{sch_uuid}")
  (paper "A4")
  (title_block
    (title "ESP32 HAR Sensor Shield")
    (date "2026-06-15")
    (rev "v1.0")
    (company "HAR Project")
    (comment 1 "MPU6050 + HMC5883L 多传感器扩展板")
    (comment 2 "2层板 60x30mm 嘉立创")
  )
  (lib_symbols)
  (sheet
    (at 0 0)
    (size 297 210)
    (fields_autoplaced)
    (stroke (width 0.1524) (type solid) (color 0 0 0 0))
    (fill (color 255 255 255 1.0000))
    (uuid "{sheet_uuid}")
{chr(10).join(symbol_lines)}
{chr(10).join(wire_lines)}
{chr(10).join(junc_lines)}
  )
  (sheet_instances
    (path "/" (page "1"))
  )
)
"""

out_dir = os.path.dirname(__file__)
with open(os.path.join(out_dir, "har-shield.kicad_sch"), "w", encoding="utf-8") as f:
    f.write(content)
print(f"Wrote har-shield.kicad_sch ({len(components)} symbols, {len(wires)} wires, {len(junctions)} junctions)")
