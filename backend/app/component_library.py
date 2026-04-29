from __future__ import annotations

from app.models import LibraryComponent, PinDefinition


def _pins(*names: str, kind: str = "passive") -> list[PinDefinition]:
    return [PinDefinition(name=name, kind=kind) for name in names]


COMPONENT_LIBRARY: dict[str, LibraryComponent] = {
    "ESP32": LibraryComponent(
        key="ESP32",
        display_name="ESP32 Dev Module",
        category="microcontroller",
        footprint="Module:ESP32-DevKitC",
        width=20,
        height=30,
        pins=_pins("3V3", "GND", "GPIO4", "GPIO5", "GPIO18", "GPIO19", "EN"),
        color="#1d4ed8",
    ),
    "Arduino Nano": LibraryComponent(
        key="Arduino Nano",
        display_name="Arduino Nano",
        category="microcontroller",
        footprint="Module:Arduino_Nano",
        width=18,
        height=43,
        pins=_pins("5V", "3V3", "GND", "D2", "D3", "D4", "A4", "A5"),
        color="#2563eb",
    ),
    "STM32F103": LibraryComponent(
        key="STM32F103",
        display_name="STM32F103 Blue Pill",
        category="microcontroller",
        footprint="Module:BluePill_STM32F103C",
        width=23,
        height=53,
        pins=_pins("3V3", "GND", "PA0", "PA1", "PA9", "PA10", "PB6", "PB7"),
        color="#1e40af",
    ),
    "DHT22": LibraryComponent(
        key="DHT22",
        display_name="DHT22 Temperature/Humidity Sensor",
        category="sensor",
        footprint="Sensor:DHT22",
        width=15,
        height=20,
        pins=_pins("VCC", "DATA", "NC", "GND"),
        color="#0f766e",
    ),
    "MPU6050": LibraryComponent(
        key="MPU6050",
        display_name="MPU6050 IMU",
        category="sensor",
        footprint="Module:MPU6050_Breakout",
        width=16,
        height=21,
        pins=_pins("VCC", "GND", "SCL", "SDA", "INT"),
        color="#0d9488",
    ),
    "HC-SR04": LibraryComponent(
        key="HC-SR04",
        display_name="HC-SR04 Ultrasonic Sensor",
        category="sensor",
        footprint="Sensor:HC-SR04",
        width=45,
        height=20,
        pins=_pins("VCC", "TRIG", "ECHO", "GND"),
        color="#0f766e",
    ),
    "BMP280": LibraryComponent(
        key="BMP280",
        display_name="BMP280 Pressure Sensor",
        category="sensor",
        footprint="Module:BMP280_Breakout",
        width=16,
        height=12,
        pins=_pins("VCC", "GND", "SCL", "SDA", "CSB", "SDO"),
        color="#14b8a6",
    ),
    "Resistor": LibraryComponent(
        key="Resistor",
        display_name="Generic Resistor",
        category="passive",
        footprint="Resistor_SMD:R_0805_2012Metric",
        width=5,
        height=2,
        pins=_pins("1", "2"),
        color="#a16207",
    ),
    "Capacitor": LibraryComponent(
        key="Capacitor",
        display_name="Generic Capacitor",
        category="passive",
        footprint="Capacitor_SMD:C_0805_2012Metric",
        width=5,
        height=2,
        pins=_pins("1", "2"),
        color="#64748b",
    ),
    "Inductor": LibraryComponent(
        key="Inductor",
        display_name="Generic Inductor",
        category="passive",
        footprint="Inductor_SMD:L_0805_2012Metric",
        width=5,
        height=3,
        pins=_pins("1", "2"),
        color="#78716c",
    ),
    "LED": LibraryComponent(
        key="LED",
        display_name="LED",
        category="discrete",
        footprint="LED_SMD:LED_0805_2012Metric",
        width=4,
        height=3,
        pins=_pins("A", "K"),
        color="#dc2626",
    ),
    "Push Button": LibraryComponent(
        key="Push Button",
        display_name="Tactile Push Button",
        category="discrete",
        footprint="Button_Switch_SMD:SW_SPST_EVQP2",
        width=6,
        height=6,
        pins=_pins("1", "2"),
        color="#475569",
    ),
    "Diode": LibraryComponent(
        key="Diode",
        display_name="Generic Diode",
        category="discrete",
        footprint="Diode_SMD:D_0805_2012Metric",
        width=4,
        height=2,
        pins=_pins("A", "K"),
        color="#7c2d12",
    ),
    "USB-C Input": LibraryComponent(
        key="USB-C Input",
        display_name="USB-C Power Input",
        category="power",
        footprint="Connector_USB:USB_C_Receptacle_USB2.0",
        width=9,
        height=7,
        pins=_pins("VBUS", "GND", "CC1", "CC2"),
        color="#111827",
    ),
    "AMS1117": LibraryComponent(
        key="AMS1117",
        display_name="AMS1117 LDO Regulator",
        category="power",
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        width=7,
        height=6,
        pins=_pins("VIN", "GND", "VOUT"),
        color="#4338ca",
    ),
    "Pin Header": LibraryComponent(
        key="Pin Header",
        display_name="2.54mm Pin Header",
        category="connector",
        footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
        width=3,
        height=12,
        pins=_pins("1", "2", "3", "4"),
        color="#334155",
    ),
    "JST-XH": LibraryComponent(
        key="JST-XH",
        display_name="JST-XH Connector",
        category="connector",
        footprint="Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
        width=8,
        height=6,
        pins=_pins("1", "2"),
        color="#334155",
    ),
}


ALIASES = {
    "esp32": "ESP32",
    "arduino nano": "Arduino Nano",
    "stm32": "STM32F103",
    "stm32f103": "STM32F103",
    "dht22": "DHT22",
    "mpu6050": "MPU6050",
    "hc-sr04": "HC-SR04",
    "hcsr04": "HC-SR04",
    "bmp280": "BMP280",
    "resistor": "Resistor",
    "capacitor": "Capacitor",
    "inductor": "Inductor",
    "led": "LED",
    "button": "Push Button",
    "push button": "Push Button",
    "diode": "Diode",
    "usb-c": "USB-C Input",
    "usb c": "USB-C Input",
    "usb": "USB-C Input",
    "ams1117": "AMS1117",
    "ldo": "AMS1117",
    "header": "Pin Header",
    "pin header": "Pin Header",
    "jst": "JST-XH",
    "jst-xh": "JST-XH",
}


def normalize_component_type(raw: str) -> str | None:
    key = raw.strip()
    if key in COMPONENT_LIBRARY:
        return key
    return ALIASES.get(key.lower())


def get_component(component_type: str) -> LibraryComponent:
    normalized = normalize_component_type(component_type)
    if not normalized:
        raise KeyError(f"Unsupported component type: {component_type}")
    return COMPONENT_LIBRARY[normalized]


def supported_component_names() -> list[str]:
    return sorted(COMPONENT_LIBRARY.keys())
