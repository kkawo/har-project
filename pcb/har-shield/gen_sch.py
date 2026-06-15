"""Generate KiCad 8 .kicad_sch for the HAR Sensor Shield."""
import uuid, os

def uid(): return str(uuid.uuid4())

# ── Symbol library definitions (embedded, portable) ────────────────────
def symbol_R(name):
    uname = name.replace(":", "_")
    return f"""(symbol "{name}"
      (pin_names (offset 0) hide)
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "R" (at 2.54 1.27 0) (id 0))
      (property "Value" "R" (at 2.54 -1.27 0) (id 1))
      (property "Footprint" "" (at 0 0 0) (id 2))
      (property "Datasheet" "~" (at 0 0 0) (id 3))
      (symbol "{uname}_0_1"
        (rectangle (start -2.54 -1.27) (end 2.54 1.27) (stroke (width 0.254) (type default)) (fill (type none)))
        (pin "1" line (at -5.08 0 0) (length 2.54) (name "1" (effects (font (size 1.27 1.27)))))
        (pin "2" line (at 5.08 0 0) (length 2.54) (name "2" (effects (font (size 1.27 1.27)))))
      )
    )"""

def symbol_C(name):
    uname = name.replace(":", "_")
    return f"""(symbol "{name}"
      (pin_names (offset 0) hide)
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "C" (at 0 2.54 0) (id 0))
      (property "Value" "C" (at 0 -2.54 0) (id 1))
      (property "Footprint" "" (at 0 0 0) (id 2))
      (property "Datasheet" "~" (at 0 0 0) (id 3))
      (symbol "{uname}_0_1"
        (pin "1" line (at -5.08 0 0) (length 2.54) (name "1" (effects (font (size 1.27 1.27)))))
        (pin "2" line (at 5.08 0 0) (length 2.54) (name "2" (effects (font (size 1.27 1.27)))))
      )
    )"""

def symbol_LED(name):
    uname = name.replace(":", "_")
    return f"""(symbol "{name}"
      (pin_names (offset 0) hide)
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "D" (at 0 2.54 0) (id 0))
      (property "Value" "LED" (at 0 -2.54 0) (id 1))
      (property "Footprint" "" (at 0 0 0) (id 2))
      (property "Datasheet" "~" (at 0 0 0) (id 3))
      (symbol "{uname}_0_1"
        (polyline (pts (xy -2.54 -1.27) (xy -2.54 1.27)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy -2.54 -1.27) (xy 2.54 0) (xy -2.54 1.27)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy 2.54 -1.27) (xy 2.54 1.27)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy 2.54 -0.635) (xy 3.81 -1.905)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy 3.175 0) (xy 2.54 0) (xy 3.81 -0.635)) (stroke (width 0.254) (type default)) (fill (type none)))
        (pin "1" line (at -5.08 0 0) (length 2.54) (name "K" (effects (font (size 1.27 1.27)))))
        (pin "2" line (at 5.08 0 0) (length 2.54) (name "A" (effects (font (size 1.27 1.27)))))
      )
    )"""

def symbol_Conn_1xN(name, n):
    """Generate a 1xN female connector symbol."""
    uname = name.replace(":", "_")
    pins = []
    top = (n - 1) * 1.27
    for i in range(n):
        y = top - i * 2.54
        pins.append(f'(pin "{i+1}" line (at -5.08 {y:.2f} 0) (length 3.81) (name "Pin_{i+1}" (effects (font (size 1.27 1.27)))))')
    return f"""(symbol "{name}"
      (pin_names (offset 1.016) hide)
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "J" (at 0 {top + 1.27:.2f} 0) (id 0))
      (property "Value" "Conn_01x{n:02d}_Female" (at 0 {-top - 1.27:.2f} 0) (id 1))
      (property "Footprint" "" (at 0 0 0) (id 2))
      (property "Datasheet" "~" (at 0 0 0) (id 3))
      (symbol "{uname}_0_1"
        (rectangle (start -1.27 {-top - 1.27:.2f}) (end 1.27 {top + 1.27:.2f}) (stroke (width 0.254) (type default)) (fill (type background)))
        {chr(10).join('        ' + p for p in pins)}
      )
    )"""

# ── Generate the schematic ─────────────────────────────────────────────
sch_uuid = uid()
sheet_uuid = uid()

lib_symbols = [
    symbol_R("har-shield-rescue:R"),
    symbol_C("har-shield-rescue:C"),
    symbol_LED("har-shield-rescue:LED"),
    symbol_Conn_1xN("har-shield-rescue:Conn_01x19_Female", 19),
    symbol_Conn_1xN("har-shield-rescue:Conn_01x08_Female", 8),
    symbol_Conn_1xN("har-shield-rescue:Conn_01x05_Female", 5),
]

# The sheet size is A4 = 297mm x 210mm
# Origin is top-left (0, 0), Y increases downward
#
# Component placement (all coordinates in mm):
#
# J1 (ESP32 LEFT, 19-pin):  at (25.4,  85.09)  — 19×2.54=48.26mm tall, centered at y=109.22
# J2 (ESP32 RIGHT, 19-pin): at (171.45, 85.09) — same height
# J3 (GY-521, 8-pin):       at (96.52,  129.54) — 8×2.54=20.32mm tall
# J4 (GY-273, 5-pin):       at (96.52,  48.26)  — 5×2.54=12.7mm tall
# R1 (SCL pull-up 4.7k):     at (63.5, 124.46)  — rotated 90°
# R2 (SDA pull-up 4.7k):     at (63.5,  111.76) — rotated 90°
# C1 (decouple GY-521):      at (149.86, 134.62)
# C2 (decouple GY-273):      at (149.86, 53.34)
# D1 (power LED):            at (40.64, 35.56)
# R3 (LED resistor 220):     at (40.64, 50.8)   — rotated 90°

# Helper: compute absolute pin positions for each component
# For a connector with N pins, placed at (cx, cy) with rotation r degrees,
# each pin i (0-indexed) has a defined position relative to the symbol origin.
# Pin positions in the symbol definition: y = top - i*2.54, x = -5.08
# After rotation 0: absolute x = cx - 5.08, absolute y = cy + (top - i*2.54)

def conn_pin_pos(cx, cy, n, pin_i, rot=0):
    """Return (x, y) of pin pin_i (1-indexed) on an N-pin connector at (cx, cy) with rotation rot."""
    i = pin_i - 1
    top = (n - 1) * 1.27
    rel_y = top - i * 2.54
    if rot == 0:   return (cx - 5.08, cy + rel_y)
    if rot == 90:  return (cx + rel_y, cy + 5.08)   # pin side faces right
    if rot == 270: return (cx - rel_y, cy - 5.08)   # pin side faces left
    return (cx + 5.08, cy - rel_y)  # rot 180

def res_pin_pos(cx, cy, pin, rot=0):
    """Pin 1 at (-5.08, 0), pin 2 at (+5.08, 0) relative. rot applies CW."""
    if pin == 1: rel_x, rel_y = -5.08, 0
    else:        rel_x, rel_y = 5.08, 0
    if rot == 0:   return (cx + rel_x, cy + rel_y)
    if rot == 90:  return (cx - rel_y, cy + rel_x)
    if rot == 180: return (cx - rel_x, cy - rel_y)
    return (cx + rel_y, cy - rel_x)  # rot 270

def cap_pin_pos(cx, cy, pin):
    """Pin 1 at (-5.08, 0), pin 2 at (+5.08, 0)."""
    if pin == 1: return (cx - 5.08, cy)
    return (cx + 5.08, cy)

def led_pin_pos(cx, cy, pin):
    """Pin 1 (K) at (-5.08, 0), pin 2 (A) at (+5.08, 0)."""
    if pin == 1: return (cx - 5.08, cy)
    return (cx + 5.08, cy)

# Component positions
# J1: left ESP32 row, 19 pins centered vertically
# J2: right ESP32 row, 19 pins centered vertically
# Both pins 1-19: pin 1 is top-most (3V3 for J1)

J1_x, J1_y = 25.4, 85.09   # top = 85.09, bottom = 85.09+48.26 = 133.35; pin1 y = 85.09-22.86=62.23? Hmm
# Actually: center_y = 109.22. top pin y = 109.22 - 22.86 = 86.36, bottom = 109.22+22.86=132.08
# Wait, the symbol origin for a connector is the center. Top pin offset = (n-1)*1.27 = 18*1.27 = 22.86mm from center
# So top pin y = center_y - 22.86, bottom = center_y + 22.86
J1_cx, J1_cy = 25.4, 109.22
J2_cx, J2_cy = 171.45, 109.22
J3_cx, J3_cy = 96.52, 129.54   # 8-pin: top offset = 7*1.27=8.89
J4_cx, J4_cy = 96.52, 48.26    # 5-pin: top offset = 4*1.27=5.08

# Key pin positions (all computed with rotation 0)
J1_3V3  = conn_pin_pos(J1_cx, J1_cy, 19, 1, 0)     # J1 pin 1 = 3V3
J1_GND  = conn_pin_pos(J1_cx, J1_cy, 19, 15, 0)    # J1 pin 15 = GND
J2_SCL  = conn_pin_pos(J2_cx, J2_cy, 19, 2, 0)     # J2 pin 2 = GPIO22/SCL
J2_SDA  = conn_pin_pos(J2_cx, J2_cy, 19, 5, 0)     # J2 pin 5 = GPIO21/SDA

J3_VCC  = conn_pin_pos(J3_cx, J3_cy, 8, 1, 0)      # GY-521 VCC
J3_GND  = conn_pin_pos(J3_cx, J3_cy, 8, 2, 0)      # GY-521 GND
J3_SCL  = conn_pin_pos(J3_cx, J3_cy, 8, 3, 0)      # GY-521 SCL
J3_SDA  = conn_pin_pos(J3_cx, J3_cy, 8, 4, 0)      # GY-521 SDA
J3_AD0  = conn_pin_pos(J3_cx, J3_cy, 8, 7, 0)      # GY-521 AD0 → GND

J4_VCC  = conn_pin_pos(J4_cx, J4_cy, 5, 1, 0)      # GY-273 VCC
J4_GND  = conn_pin_pos(J4_cx, J4_cy, 5, 2, 0)      # GY-273 GND
J4_SCL  = conn_pin_pos(J4_cx, J4_cy, 5, 3, 0)      # GY-273 SCL
J4_SDA  = conn_pin_pos(J4_cx, J4_cy, 5, 4, 0)      # GY-273 SDA

# Resistors and caps
R1_cx, R1_cy = 63.5, 124.46   # SCL pull-up, rotated 90°
R2_cx, R2_cy = 63.5, 111.76   # SDA pull-up, rotated 90°
C1_cx, C1_cy = 149.86, 134.62  # GY-521 decoupling
C2_cx, C2_cy = 149.86, 53.34   # GY-273 decoupling
D1_cx, D1_cy = 40.64, 35.56
R3_cx, R3_cy = 40.64, 50.8    # LED resistor, rotated 90°

R1_1 = res_pin_pos(R1_cx, R1_cy, 1, 90)
R1_2 = res_pin_pos(R1_cx, R1_cy, 2, 90)
R2_1 = res_pin_pos(R2_cx, R2_cy, 1, 90)
R2_2 = res_pin_pos(R2_cx, R2_cy, 2, 90)
C1_1 = cap_pin_pos(C1_cx, C1_cy, 1)
C1_2 = cap_pin_pos(C1_cx, C1_cy, 2)
C2_1 = cap_pin_pos(C2_cx, C2_cy, 1)
C2_2 = cap_pin_pos(C2_cx, C2_cy, 2)
D1_K = led_pin_pos(D1_cx, D1_cy, 1)
D1_A = led_pin_pos(D1_cx, D1_cy, 2)
R3_1 = res_pin_pos(R3_cx, R3_cy, 1, 90)
R3_2 = res_pin_pos(R3_cx, R3_cy, 2, 90)

wires = []
junctions = set()

def add_wire(x1, y1, x2, y2):
    wires.append((x1, y1, x2, y2))

def add_junction(x, y):
    junctions.add((round(x, 4), round(y, 4)))

def route_hv(sx, sy, ex, ey):
    """Route with one corner: horizontal then vertical."""
    add_wire(sx, sy, ex, sy)
    add_wire(ex, sy, ex, ey)
    add_junction(ex, sy)

def route_vh(sx, sy, ex, ey):
    """Route with one corner: vertical then horizontal."""
    add_wire(sx, sy, sx, ey)
    add_wire(sx, ey, ex, ey)
    add_junction(sx, ey)

# ── Power net (+3V3) ───────────────────────────────────────────────────
# J1-1(3V3) → bus line at y=35
bus_3v3_y = 30.0
bus_3v3_x_start = J1_3V3[0]
bus_3v3_x_end = 155.0

# horizontal 3V3 bus
add_wire(bus_3v3_x_start, bus_3v3_y, bus_3v3_x_end, bus_3v3_y)
# J1-1 to bus
add_wire(J1_3V3[0], J1_3V3[1], J1_3V3[0], bus_3v3_y)
add_junction(J1_3V3[0], bus_3v3_y)

# R1-1 to bus (pull-up): R1_1 rotated 90°, pin 1 faces top
# R1_1 = pin 1 of rotated resistor (at top now)
route_hv(R1_1[0], R1_1[1], R1_1[0], bus_3v3_y)
add_junction(R1_1[0], bus_3v3_y)

# R2-1 to bus
route_hv(R2_1[0], R2_1[1], R2_1[0], bus_3v3_y)
add_junction(R2_1[0], bus_3v3_y)

# C1-1 to bus
route_hv(C1_1[0], C1_1[1], C1_1[0], bus_3v3_y)
add_junction(C1_1[0], bus_3v3_y)

# C2-1 to bus
route_hv(C2_1[0], C2_1[1], C2_1[0], bus_3v3_y)
add_junction(C2_1[0], bus_3v3_y)

# R3-1 to bus
route_hv(R3_1[0], R3_1[1], R3_1[0], bus_3v3_y)
add_junction(R3_1[0], bus_3v3_y)

# J3-1 (GY-521 VCC) to bus
route_hv(J3_VCC[0], J3_VCC[1], J3_VCC[0], bus_3v3_y)
add_junction(J3_VCC[0], bus_3v3_y)

# J4-1 (GY-273 VCC) to bus
route_hv(J4_VCC[0], J4_VCC[1], J4_VCC[0], bus_3v3_y)
add_junction(J4_VCC[0], bus_3v3_y)

# ── R3-2 → D1-A ───────────────────────────────────────────────────────
# R3 rotated 90°, pin 2 faces down
add_wire(R3_2[0], R3_2[1], R3_2[0], D1_A[1])
add_wire(R3_2[0], D1_A[1], D1_A[0], D1_A[1])

# ── Ground net (GND) ───────────────────────────────────────────────────
bus_gnd_y = 155.0
add_wire(20.0, bus_gnd_y, 160.0, bus_gnd_y)

# J1-15 (GND) to bus
add_wire(J1_GND[0], J1_GND[1], J1_GND[0], bus_gnd_y)
add_junction(J1_GND[0], bus_gnd_y)

# J3-2 (GY-521 GND) to bus
route_hv(J3_GND[0], J3_GND[1], J3_GND[0], bus_gnd_y)
add_junction(J3_GND[0], bus_gnd_y)

# J4-2 (GY-273 GND) to bus
route_hv(J4_GND[0], J4_GND[1], J4_GND[0], bus_gnd_y)
add_junction(J4_GND[0], bus_gnd_y)

# C1-2 to bus
route_hv(C1_2[0], C1_2[1], C1_2[0], bus_gnd_y)
add_junction(C1_2[0], bus_gnd_y)

# C2-2 to bus
route_hv(C2_2[0], C2_2[1], C2_2[0], bus_gnd_y)
add_junction(C2_2[0], bus_gnd_y)

# D1-K to bus
route_hv(D1_K[0], D1_K[1], D1_K[0], bus_gnd_y)
add_junction(D1_K[0], bus_gnd_y)

# J3-7 (AD0) to GND bus
route_hv(J3_AD0[0], J3_AD0[1], J3_AD0[0], bus_gnd_y)
add_junction(J3_AD0[0], bus_gnd_y)

# ── SCL net ────────────────────────────────────────────────────────────
bus_scl_y = 140.0
add_wire(55.0, bus_scl_y, 110.0, bus_scl_y)

# R1-2 (SCL pull-up output)
route_hv(R1_2[0], R1_2[1], R1_2[0], bus_scl_y)
add_junction(R1_2[0], bus_scl_y)

# J2-2 (ESP32 SCL)
route_hv(J2_SCL[0], J2_SCL[1], J2_SCL[0], bus_scl_y)
add_junction(J2_SCL[0], bus_scl_y)

# J3-3 (GY-521 SCL)
route_hv(J3_SCL[0], J3_SCL[1], J3_SCL[0], bus_scl_y)
add_junction(J3_SCL[0], bus_scl_y)

# J4-3 (GY-273 SCL)
route_hv(J4_SCL[0], J4_SCL[1], J4_SCL[0], bus_scl_y)
add_junction(J4_SCL[0], bus_scl_y)

# ── SDA net ────────────────────────────────────────────────────────────
bus_sda_y = 145.0
add_wire(55.0, bus_sda_y, 110.0, bus_sda_y)

# R2-2 (SDA pull-up output)
route_hv(R2_2[0], R2_2[1], R2_2[0], bus_sda_y)
add_junction(R2_2[0], bus_sda_y)

# J2-5 (ESP32 SDA)
route_hv(J2_SDA[0], J2_SDA[1], J2_SDA[0], bus_sda_y)
add_junction(J2_SDA[0], bus_sda_y)

# J3-4 (GY-521 SDA)
route_hv(J3_SDA[0], J3_SDA[1], J3_SDA[0], bus_sda_y)
add_junction(J3_SDA[0], bus_sda_y)

# J4-4 (GY-273 SDA)
route_hv(J4_SDA[0], J4_SDA[1], J4_SDA[0], bus_sda_y)
add_junction(J4_SDA[0], bus_sda_y)

# ── Write the file ─────────────────────────────────────────────────────
def sch_symbol(lib, ref, val, fp, at_x, at_y, rot, pins):
    """Generate a (symbol ...) entry."""
    pin_lines = "\n".join(
        f'      (pin "{p}" (uuid "{uid()}"))'
        for p in pins
    )
    return f"""(symbol
      (lib_id "{lib}")
      (at {at_x:.2f} {at_y:.2f} {rot})
      (uuid "{uid()}")
      (property "Reference" "{ref}" (at {at_x:.2f} {at_y - 5.08:.2f} 0) (id 0))
      (property "Value" "{val}" (at {at_x:.2f} {at_y + 5.08:.2f} 0) (id 1))
      (property "Footprint" "{fp}" (at {at_x:.2f} {at_y:.2f} 0) (id 2))
      (property "Datasheet" "" (at {at_x:.2f} {at_y:.2f} 0) (id 3))
{pin_lines}
    )"""

symbols_sch = [
    sch_symbol("har-shield-rescue:Conn_01x19_Female", "J1", "ESP32_LEFT",
               "Connector_PinHeader_2.54mm:PinHeader_1x19_P2.54mm_Vertical",
               J1_cx, J1_cy, 0, list(range(1, 20))),
    sch_symbol("har-shield-rescue:Conn_01x19_Female", "J2", "ESP32_RIGHT",
               "Connector_PinHeader_2.54mm:PinHeader_1x19_P2.54mm_Vertical",
               J2_cx, J2_cy, 0, list(range(1, 20))),
    sch_symbol("har-shield-rescue:Conn_01x08_Female", "J3", "GY-521_MPU6050",
               "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
               J3_cx, J3_cy, 0, list(range(1, 9))),
    sch_symbol("har-shield-rescue:Conn_01x05_Female", "J4", "GY-273_HMC5883L",
               "Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical",
               J4_cx, J4_cy, 0, list(range(1, 6))),
    sch_symbol("har-shield-rescue:R", "R1", "4.7k",
               "Resistor_SMD:R_0805_2012Metric",
               R1_cx, R1_cy, 90, [1, 2]),
    sch_symbol("har-shield-rescue:R", "R2", "4.7k",
               "Resistor_SMD:R_0805_2012Metric",
               R2_cx, R2_cy, 90, [1, 2]),
    sch_symbol("har-shield-rescue:C", "C1", "100nF",
               "Capacitor_SMD:C_0805_2012Metric",
               C1_cx, C1_cy, 0, [1, 2]),
    sch_symbol("har-shield-rescue:C", "C2", "100nF",
               "Capacitor_SMD:C_0805_2012Metric",
               C2_cx, C2_cy, 0, [1, 2]),
    sch_symbol("har-shield-rescue:LED", "D1", "LED",
               "LED_SMD:LED_0805_2012Metric",
               D1_cx, D1_cy, 0, [1, 2]),
    sch_symbol("har-shield-rescue:R", "R3", "220",
               "Resistor_SMD:R_0805_2012Metric",
               R3_cx, R3_cy, 90, [1, 2]),
]

wire_lines = []
for x1, y1, x2, y2 in wires:
    wire_lines.append(
        f'  (wire (pts (xy {x1:.2f} {y1:.2f}) (xy {x2:.2f} {y2:.2f})) (stroke (width 0.1524) (type default)) (uuid "{uid()}"))'
    )

junc_lines = []
for x, y in sorted(junctions):
    junc_lines.append(
        f'  (junction (at {x:.2f} {y:.2f}) (diameter 1.016) (color 0 0 0 0) (uuid "{uid()}"))'
    )

lib_section = "\n".join(f"    {s}" for s in lib_symbols)
symbol_section = "\n".join(symbols_sch)
wire_section = "\n".join(wire_lines)
junc_section = "\n".join(junc_lines)

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
    (comment 2 "2层板 ≤60x30mm · 嘉立创")
  )
  (lib_symbols
{lib_section}
  )
  (sheet
    (at 0 0)
    (size 297 210)
    (fields_autoplaced)
    (stroke (width 0.1524) (type solid) (color 0 0 0 0))
    (fill (color 255 255 255 1.0000))
    (uuid "{sheet_uuid}")
{symbol_section}
{wire_section}
{junc_section}
  )
  (sheet_instances
    (path "/" (page "1"))
  )
)
"""

out_path = os.path.join(os.path.dirname(__file__), "har-shield.kicad_sch")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(content)
print(f"Wrote {out_path}")
print(f"  {len(symbols_sch) // 10} symbols, {len(wires)} wires, {len(junctions)} junctions")
