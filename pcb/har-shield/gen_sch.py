"""Generate KiCad 8 .kicad_sch for ESP32-S3 44-pin HAR Shield."""
import uuid, os

def uid(): return str(uuid.uuid4())

sch_uuid = uid()
sheet_uuid = uid()

# ═══════════════════════════════════════════════════════════════════════
# Embedded symbol: 1x22 Female (not in standard KiCad library)
# ═══════════════════════════════════════════════════════════════════════
sym_22_name = "shield_Conn_01x22_Female"
sym_22_unit = "shield_Conn_01x22_Female_0_1"

def embed_22pin():
    pins = []
    top = 21 * 1.27  # 26.67
    for i in range(22):
        y = top - i * 2.54
        pins.append(
            f'(pin "{i+1}" passive line (at -5.08 {y:.2f} 0) '
            f'(length 3.81) '
            f'(name "Pin_{i+1}" (effects (font (size 1.27 1.27)))))'
        )
    return f"""(symbol "{sym_22_name}"
      (pin_names (offset 1.016) hide)
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "J" (at 0 {top + 1.27:.2f} 0) (id 0))
      (property "Value" "Conn_01x22" (at 0 {-top - 1.27:.2f} 0) (id 1))
      (property "Footprint" "" (at 0 0 0) (id 2))
      (property "Datasheet" "~" (at 0 0 0) (id 3))
      (symbol "{sym_22_unit}"
        (rectangle
          (start -1.27 {-top - 1.27:.2f}) (end 1.27 {top + 1.27:.2f})
          (stroke (width 0.254) (type default)) (fill (type background)))
{chr(10).join(pins)}
      )
    )"""

# ═══════════════════════════════════════════════════════════════════════
# Component placements  (all coords in mm on A4 = 297×210)
# ═══════════════════════════════════════════════════════════════════════

J1_x, J1_y = 25.4, 109.22     # ESP32-S3 LEFT  (22-pin)
J2_x, J2_y = 171.45, 109.22    # ESP32-S3 RIGHT (22-pin)
J3_x, J3_y = 96.52, 135.0      # GY-521  (8-pin)
J4_x, J4_y = 96.52, 50.0       # GY-273  (5-pin)
R1_x, R1_y = 63.5, 124.46      # SCL pull-up 4.7k  (rotated 90)
R2_x, R2_y = 63.5, 111.76      # SDA pull-up 4.7k  (rotated 90)
C1_x, C1_y = 149.86, 140.0     # decouple GY-521
C2_x, C2_y = 149.86, 53.0      # decouple GY-273
D1_x, D1_y = 40.64, 35.56      # power LED
R3_x, R3_y = 40.64, 50.8       # LED resistor 220  (rotated 90)

components = [
    # (lib_id, ref, value, footprint, x, y, rot, npins)
    (sym_22_name, "J1", "ESP32_LEFT",   "Connector_PinHeader_2.54mm:PinHeader_1x22_P2.54mm_Vertical", J1_x, J1_y, 0, 22),
    (sym_22_name, "J2", "ESP32_RIGHT",  "Connector_PinHeader_2.54mm:PinHeader_1x22_P2.54mm_Vertical", J2_x, J2_y, 0, 22),
    ("Connector_Generic:Conn_01x08_Female", "J3", "GY-521_MPU6050",  "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical", J3_x, J3_y, 0, 8),
    ("Connector_Generic:Conn_01x05_Female", "J4", "GY-273_HMC5883L", "Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical", J4_x, J4_y, 0, 5),
    ("Device:R", "R1", "4.7k",  "Resistor_SMD:R_0805_2012Metric",  R1_x, R1_y, 90, 2),
    ("Device:R", "R2", "4.7k",  "Resistor_SMD:R_0805_2012Metric",  R2_x, R2_y, 90, 2),
    ("Device:C", "C1", "100nF", "Capacitor_SMD:C_0805_2012Metric", C1_x, C1_y, 0,  2),
    ("Device:C", "C2", "100nF", "Capacitor_SMD:C_0805_2012Metric", C2_x, C2_y, 0,  2),
    ("Device:LED", "D1", "LED", "LED_SMD:LED_0805_2012Metric",      D1_x, D1_y, 0,  2),
    ("Device:R", "R3", "220",   "Resistor_SMD:R_0805_2012Metric",  R3_x, R3_y, 90, 2),
]

# ═══════════════════════════════════════════════════════════════════════
# Pin coordinate helpers
# ═══════════════════════════════════════════════════════════════════════

def conn_pin(cx, cy, n, pin_i):
    """Absolute (x,y) of pin_i (1-indexed) on an N-pin connector symbol at (cx,cy), rot=0."""
    top = (n - 1) * 1.27
    return (cx - 5.08, cy + top - (pin_i - 1) * 2.54)

def dev_pin(cx, cy, pin, rot=0):
    """Absolute (x,y) of pin 1 or 2 of a Device symbol (R/C/LED)."""
    if pin == 1: rx, ry = -5.08, 0.0
    else:        rx, ry = 5.08, 0.0
    if rot == 0:   return (cx + rx, cy + ry)
    if rot == 90:  return (cx - ry, cy + rx)
    if rot == 180: return (cx - rx, cy - ry)
    return (cx + ry, cy - rx)       # rot 270

# ── Key positions ────────────────────────────────────────────────────
# J1 (LEFT):  pin 1=3V3, pin 10=IO17(SDA), pin 11=IO18(SCL), pin 22=GND
J1_3V3  = conn_pin(J1_x, J1_y, 22, 1)
J1_SDA  = conn_pin(J1_x, J1_y, 22, 10)
J1_SCL  = conn_pin(J1_x, J1_y, 22, 11)
J1_GND  = conn_pin(J1_x, J1_y, 22, 22)

# J2 (RIGHT): not used for signals, just pass-through

# J3 (GY-521): pin 1=VCC, 2=GND, 3=SCL, 4=SDA, 7=AD0
J3_VCC  = conn_pin(J3_x, J3_y, 8, 1)
J3_GND  = conn_pin(J3_x, J3_y, 8, 2)
J3_SCL  = conn_pin(J3_x, J3_y, 8, 3)
J3_SDA  = conn_pin(J3_x, J3_y, 8, 4)
J3_AD0  = conn_pin(J3_x, J3_y, 8, 7)

# J4 (GY-273): pin 1=VCC, 2=GND, 3=SCL, 4=SDA
J4_VCC  = conn_pin(J4_x, J4_y, 5, 1)
J4_GND  = conn_pin(J4_x, J4_y, 5, 2)
J4_SCL  = conn_pin(J4_x, J4_y, 5, 3)
J4_SDA  = conn_pin(J4_x, J4_y, 5, 4)

# Resistors & caps & LED
R1_1 = dev_pin(R1_x, R1_y, 1, 90); R1_2 = dev_pin(R1_x, R1_y, 2, 90)
R2_1 = dev_pin(R2_x, R2_y, 1, 90); R2_2 = dev_pin(R2_x, R2_y, 2, 90)
C1_1 = dev_pin(C1_x, C1_y, 1, 0);  C1_2 = dev_pin(C1_x, C1_y, 2, 0)
C2_1 = dev_pin(C2_x, C2_y, 1, 0);  C2_2 = dev_pin(C2_x, C2_y, 2, 0)
D1_K = dev_pin(D1_x, D1_y, 1, 0);  D1_A = dev_pin(D1_x, D1_y, 2, 0)
R3_1 = dev_pin(R3_x, R3_y, 1, 90); R3_2 = dev_pin(R3_x, R3_y, 2, 90)

# ═══════════════════════════════════════════════════════════════════════
# Wires  (bus-line style: horizontal buses for each net)
# ═══════════════════════════════════════════════════════════════════════
wires = []
juncs = set()

def W(x1,y1,x2,y2): wires.append((x1,y1,x2,y2))
def J(x,y): juncs.add((round(x,4), round(y,4)))
def H(sx,sy, ex,ey):  # route: go sideways to ex, then vertical to ey
    W(sx,sy, ex,sy); W(ex,sy, ex,ey); J(ex,sy)

# ── +3V3 bus (horizontal at y=22) ────────────────────────────────────
bus3v3_y = 22.0
W(20.0, bus3v3_y, 160.0, bus3v3_y)
for px, py in [J1_3V3, J3_VCC, J4_VCC, R1_1, R2_1, C1_1, C2_1, R3_1]:
    H(px, py, px, bus3v3_y); J(px, bus3v3_y)

# ── GND bus (horizontal at y=158) ────────────────────────────────────
gnd_y = 158.0
W(20.0, gnd_y, 165.0, gnd_y)
for px, py in [J1_GND, J3_GND, J4_GND, J3_AD0, C1_2, C2_2, D1_K]:
    H(px, py, px, gnd_y); J(px, gnd_y)

# ── SCL bus (horizontal at y=140) ────────────────────────────────────
scl_y = 140.0
W(55.0, scl_y, 110.0, scl_y)
for px, py in [J1_SCL, R1_2, J3_SCL, J4_SCL]:
    H(px, py, px, scl_y); J(px, scl_y)

# ── SDA bus (horizontal at y=146) ────────────────────────────────────
sda_y = 146.0
W(55.0, sda_y, 110.0, sda_y)
for px, py in [J1_SDA, R2_2, J3_SDA, J4_SDA]:
    H(px, py, px, sda_y); J(px, sda_y)

# ── LED: R3_2 → D1_A ────────────────────────────────────────────────
W(R3_2[0], R3_2[1], R3_2[0], D1_A[1])
W(R3_2[0], D1_A[1], D1_A[0], D1_A[1])

# ═══════════════════════════════════════════════════════════════════════
# Generate .kicad_sch
# ═══════════════════════════════════════════════════════════════════════

def fmt_pt(x,y):
    return f"{x:.2f} {y:.2f}"

symbol_lines = []
for lib_id, ref, val, fp, cx, cy, rot, npins in components:
    pin_block = "\n".join(f'      (pin "{p}" (uuid "{uid()}"))' for p in range(1, npins + 1))
    symbol_lines.append(f"""(symbol
      (lib_id "{lib_id}")
      (at {fmt_pt(cx, cy)} {rot})
      (uuid "{uid()}")
      (property "Reference" "{ref}" (at {fmt_pt(cx, cy - 7.62)} 0) (id 0))
      (property "Value" "{val}" (at {fmt_pt(cx, cy + 7.62)} 0) (id 1))
      (property "Footprint" "{fp}" (at {fmt_pt(cx, cy)} 0) (id 2))
      (property "Datasheet" "" (at {fmt_pt(cx, cy)} 0) (id 3))
{pin_block}
    )""")

wire_lines  = [f'  (wire (pts (xy {fmt_pt(x1,y1)}) (xy {fmt_pt(x2,y2)})) (stroke (width 0.1524) (type default)) (uuid "{uid()}"))' for x1,y1,x2,y2 in wires]
junc_lines  = [f'  (junction (at {fmt_pt(x,y)}) (diameter 1.016) (color 0 0 0 0) (uuid "{uid()}"))' for x,y in sorted(juncs)]

content = f"""(kicad_sch
  (version 20231120)
  (generator "eeschema")
  (generator_version "8.0")
  (uuid "{sch_uuid}")
  (paper "A4")
  (title_block
    (title "ESP32-S3 HAR Sensor Shield")
    (date "2026-06-15")
    (rev "v1.0")
    (company "HAR Project")
    (comment 1 "MPU6050 + HMC5883L 2层板 60x30mm")
    (comment 2 "IO17=SDA IO18=SCL 嘉立创")
  )
  (lib_symbols
    {embed_22pin()}
  )
  (sheet
    (at 0 0)
    (size 297 210)
    (fields_autoplaced yes)
    (stroke (width 0.1524) (type solid))
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

out = os.path.join(os.path.dirname(__file__), "har-shield.kicad_sch")
with open(out, "w", encoding="utf-8") as f:
    f.write(content)
print(f"OK → {out}")
print(f"  {len(components)} symbols  |  {len(wires)} wires  |  {len(juncs)} junctions")
print(f"  Pin mapping: J1-1=3V3  J1-10=SDA(IO17)  J1-11=SCL(IO18)  J1-22=GND")
