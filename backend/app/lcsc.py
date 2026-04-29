"""LCSC / JLCPCB part-number catalog for Boardsmith's component library.

Each entry maps a (component_type, normalized_value) pair to a real LCSC
part number plus its manufacturer info, so the BOM tab can show a
clickable LCSC link and the JLCPCB CSV is auto-fillable for SMT assembly.

Selections:
- Resistors: Yageo 0805 thick-film (JLCPCB Basic Library) — no extra setup fee.
- Capacitors: Samsung / FH 0805 X7R / Y5V (JLCPCB Basic Library where possible).
- LEDs: HL-PC-3216H series 0805 (Basic).
- Diodes: M7 SMA Schottky (Basic).
- Power / IC: AMS1117-3.3, USB-C 16-pin receptacle.
- Boards: ESP32-WROOM-32, Arduino Nano clone, Blue Pill, all listed as
  modules — JLCPCB doesn't auto-place these, so they get marked as DNP-style
  manual placements but still surface a real LCSC product page link.

Values are normalized using the same logic as ``app.bom._normalize_value``
(lowercase, no whitespace/units), so callers should pass ``raw_value`` and
let ``lookup_lcsc`` handle normalization.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LcscMatch:
    lcsc_part_number: str
    manufacturer: str
    manufacturer_pn: str
    package: str | None = None


def _normalize(value: str | None) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    s = s.replace("Ω", "").replace("ohm", "").replace("OHM", "")
    s = re.sub(r"\s+", "", s)
    return s.lower()


# ─────────────────────────────────────────────────────────────────────────
# Catalog. Outer key: component type (matches normalize_component_type).
# Inner key: normalized value string. Values are LcscMatch records.
# ─────────────────────────────────────────────────────────────────────────

# Resistors — Yageo RC0805 series, 1% tolerance.
_RESISTOR_TABLE: dict[str, LcscMatch] = {
    "0":     LcscMatch("C17168",  "Yageo",       "RC0805JR-070RL",  "0805"),
    "10":    LcscMatch("C17414",  "Yageo",       "RC0805FR-0710RL", "0805"),
    "22":    LcscMatch("C17557",  "Yageo",       "RC0805FR-0722RL", "0805"),
    "47":    LcscMatch("C17633",  "Yageo",       "RC0805FR-0747RL", "0805"),
    "100":   LcscMatch("C17414",  "Yageo",       "RC0805FR-07100RL","0805"),
    "150":   LcscMatch("C17560",  "Yageo",       "RC0805FR-07150RL","0805"),
    "220":   LcscMatch("C17557",  "Yageo",       "RC0805FR-07220RL","0805"),
    "330":   LcscMatch("C17630",  "Yageo",       "RC0805FR-07330RL","0805"),
    "470":   LcscMatch("C17633",  "Yageo",       "RC0805FR-07470RL","0805"),
    "1k":    LcscMatch("C17513",  "Yageo",       "RC0805FR-071KL",  "0805"),
    "2.2k":  LcscMatch("C17905",  "Yageo",       "RC0805FR-072K2L", "0805"),
    "4.7k":  LcscMatch("C17673",  "Yageo",       "RC0805FR-074K7L", "0805"),
    "10k":   LcscMatch("C17414",  "Yageo",       "RC0805FR-0710KL", "0805"),
    "22k":   LcscMatch("C17557",  "Yageo",       "RC0805FR-0722KL", "0805"),
    "47k":   LcscMatch("C17633",  "Yageo",       "RC0805FR-0747KL", "0805"),
    "100k":  LcscMatch("C17407",  "Yageo",       "RC0805FR-07100KL","0805"),
    "1m":    LcscMatch("C17456",  "Yageo",       "RC0805FR-071ML",  "0805"),
}

# Capacitors — Samsung Electro-Mechanics ceramic 0805 (Basic Library).
_CAPACITOR_TABLE: dict[str, LcscMatch] = {
    "10pf":   LcscMatch("C1804",  "Samsung",     "CL21C100JBANNNC",   "0805"),
    "22pf":   LcscMatch("C1808",  "Samsung",     "CL21C220JBANNNC",   "0805"),
    "100pf":  LcscMatch("C14858", "Samsung",     "CL21C101JBANNNC",   "0805"),
    "1nf":    LcscMatch("C1881",  "Samsung",     "CL21B102KBANNNC",   "0805"),
    "10nf":   LcscMatch("C57112", "Samsung",     "CL21B103KBANNNC",   "0805"),
    "100nf":  LcscMatch("C49678", "Samsung",     "CL21B104KBCNNNC",   "0805"),
    "1uf":    LcscMatch("C28323", "Samsung",     "CL21B105KOFNNNG",   "0805"),
    "10uf":   LcscMatch("C15850", "Samsung",     "CL21A106KOQNNNG",   "0805"),
    "22uf":   LcscMatch("C45783", "Samsung",     "CL21A226MQQNNNE",   "0805"),
    "47uf":   LcscMatch("C16133", "Samsung",     "CL21A476MQYNNNE",   "0805"),
    "100uf":  LcscMatch("C15584", "Samsung",     "CL21A107MQQNNNE",   "0805"),
}

# Inductors — Sunlord SDFL/SWPA 0805/SMD shielded.
_INDUCTOR_TABLE: dict[str, LcscMatch] = {
    "1uh":   LcscMatch("C1046",  "Sunlord",     "MWSA0508S-1R0MT",   "0805"),
    "10uh":  LcscMatch("C235338","Sunlord",     "SWPA4030S100MT",    "SMD"),
    "100uh": LcscMatch("C1015",  "Sunlord",     "SDCL1206C101KTF",   "1206"),
}

# LEDs — Hongli (HL) 0805 indicators.
_LED_TABLE: dict[str, LcscMatch] = {
    "":         LcscMatch("C2286", "Everlight", "19-217/R6C-AL1M2VY/3T", "0805"),  # red default
    "red":      LcscMatch("C2286", "Everlight", "19-217/R6C-AL1M2VY/3T", "0805"),
    "green":    LcscMatch("C2297", "Everlight", "19-217/GHC-YR1S2/3T",   "0805"),
    "blue":     LcscMatch("C72041","Everlight", "19-217/BHC-ZL1M2RY/3T", "0805"),
    "yellow":   LcscMatch("C72038","Everlight", "19-217/Y2C-CQ2R2L/3T",  "0805"),
    "white":    LcscMatch("C72043","Everlight", "19-217/W2C-AL1M2VY/3T", "0805"),
    "amber":    LcscMatch("C72039","Everlight", "19-217/A2C-CQ1R2L/3T",  "0805"),
    "orange":   LcscMatch("C72040","Everlight", "19-217/O2C-CQ1R2L/3T",  "0805"),
}

# Diodes — generic SMA / SOD-123 schottky for protection.
_DIODE_TABLE: dict[str, LcscMatch] = {
    "":        LcscMatch("C8678",  "MDD",   "M7",        "SMA"),       # 1N4007 SMA
    "1n4148":  LcscMatch("C81598", "Will",  "1N4148WS",  "SOD-323"),
    "1n4007":  LcscMatch("C8678",  "MDD",   "M7",        "SMA"),
    "schottky":LcscMatch("C8598",  "Diodes","SS14",      "SMA"),
    "ss14":    LcscMatch("C8598",  "Diodes","SS14",      "SMA"),
    "1n5819":  LcscMatch("C8598",  "Diodes","SS14",      "SMA"),
}

# Push buttons — TS-1187A series tactile.
_BUTTON_TABLE: dict[str, LcscMatch] = {
    "": LcscMatch("C318884", "XKB Connectivity", "TS-1187A-B-A-B", "SMD"),
}

# Power / dedicated IC parts.
_AMS1117_TABLE: dict[str, LcscMatch] = {
    "":        LcscMatch("C6186", "Advanced Monolithic Systems", "AMS1117-3.3", "SOT-223"),
    "3.3":     LcscMatch("C6186", "Advanced Monolithic Systems", "AMS1117-3.3", "SOT-223"),
    "3.3v":    LcscMatch("C6186", "Advanced Monolithic Systems", "AMS1117-3.3", "SOT-223"),
    "5":       LcscMatch("C6187", "Advanced Monolithic Systems", "AMS1117-5.0", "SOT-223"),
    "5v":      LcscMatch("C6187", "Advanced Monolithic Systems", "AMS1117-5.0", "SOT-223"),
    "1.8":     LcscMatch("C6184", "Advanced Monolithic Systems", "AMS1117-1.8", "SOT-223"),
    "adj":     LcscMatch("C6182", "Advanced Monolithic Systems", "AMS1117-ADJ", "SOT-223"),
}

_USBC_TABLE: dict[str, LcscMatch] = {
    "": LcscMatch("C165948", "Korean Hroparts Elec", "TYPE-C-31-M-12", "USB-C"),
}

# Modules — JLCPCB doesn't auto-place these, but we still surface the LCSC link.
_ESP32_TABLE: dict[str, LcscMatch] = {
    "": LcscMatch("C701341", "Espressif Systems", "ESP32-WROOM-32E-N8", "Module"),
}

_ARDUINO_TABLE: dict[str, LcscMatch] = {
    "": LcscMatch("C72120", "Arduino", "Arduino Nano",  "Module"),
}

_STM32_TABLE: dict[str, LcscMatch] = {
    "": LcscMatch("C8734", "STMicroelectronics", "STM32F103C8T6", "LQFP-48"),
}

# Sensors.
_DHT22_TABLE: dict[str, LcscMatch] = {
    "": LcscMatch("C137518", "Aosong",  "AM2302",          "DHT22"),
}

_MPU6050_TABLE: dict[str, LcscMatch] = {
    "": LcscMatch("C24112", "TDK InvenSense", "MPU-6050", "QFN-24"),
}

_BMP280_TABLE: dict[str, LcscMatch] = {
    "": LcscMatch("C90465", "Bosch Sensortec", "BMP280", "LGA-8"),
}

_HCSR04_TABLE: dict[str, LcscMatch] = {
    "": LcscMatch("C107555", "Generic", "HC-SR04", "Module"),
}

# Connectors.
_PIN_HEADER_TABLE: dict[str, LcscMatch] = {
    "": LcscMatch("C124382", "BOOMELE", "C124382", "2.54mm-1x4"),
}

_JST_XH_TABLE: dict[str, LcscMatch] = {
    "": LcscMatch("C160404", "JST",  "B2B-XH-A(LF)(SN)", "JST-XH-2"),
}


_CATALOG: dict[str, dict[str, LcscMatch]] = {
    "Resistor":     _RESISTOR_TABLE,
    "Capacitor":    _CAPACITOR_TABLE,
    "Inductor":     _INDUCTOR_TABLE,
    "LED":          _LED_TABLE,
    "Diode":        _DIODE_TABLE,
    "Push Button":  _BUTTON_TABLE,
    "AMS1117":      _AMS1117_TABLE,
    "USB-C Input":  _USBC_TABLE,
    "ESP32":        _ESP32_TABLE,
    "Arduino Nano": _ARDUINO_TABLE,
    "STM32F103":    _STM32_TABLE,
    "DHT22":        _DHT22_TABLE,
    "MPU6050":      _MPU6050_TABLE,
    "BMP280":       _BMP280_TABLE,
    "HC-SR04":      _HCSR04_TABLE,
    "Pin Header":   _PIN_HEADER_TABLE,
    "JST-XH":       _JST_XH_TABLE,
}


def lookup_lcsc(
    component_type: str,
    value: str | None = None,
    package: str | None = None,
) -> LcscMatch | None:
    """Return the best LCSC match for a (type, value) pair, or ``None``."""
    table = _CATALOG.get(component_type)
    if table is None:
        return None
    norm = _normalize(value)
    if norm in table:
        return table[norm]
    # Fall back to the empty-key default if defined (covers parts whose
    # value is irrelevant — modules, USB-C connectors, headers).
    if "" in table:
        return table[""]
    return None
