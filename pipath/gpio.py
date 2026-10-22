"""GPIO helpers for the app: Simulator vs Real Pi, wiring parts, the 40-pin header, wiring checks."""
from __future__ import annotations

import os
import re
from pathlib import Path

SHIM = Path(__file__).resolve().parent / "gpio_shim.py"

SIM_ENV = {"GPIOZERO_PIN_FACTORY": "mock", "GPIOZERO_MOCK_PIN_CLASS": "mockpwmpin"}

# What each gpiozero class looks like on the on-screen board
BOARD_KIND = {
    "Servo": "servo", "AngularServo": "servo",
    "LED": "led", "PWMLED": "led", "OutputDevice": "led", "DigitalOutputDevice": "led",
    "PWMOutputDevice": "led", "Buzzer": "buzzer", "TonalBuzzer": "buzzer",
    "Button": "button", "MotionSensor": "pir", "RGBLED": "rgbled", "DistanceSensor": "distance",
    "LineSensor": "switch", "LightSensor": "switch", "DigitalInputDevice": "switch", "InputDevice": "switch",
}
INPUT_KINDS = {"button", "switch", "pir"}

# Physical header pin -> what it is (Raspberry Pi 3B, 40 pins). Ints are GPIO (BCM) numbers.
HEADER = {
    1: "3V3", 2: "5V", 3: 2, 4: "5V", 5: 3, 6: "GND", 7: 4, 8: 14, 9: "GND", 10: 15,
    11: 17, 12: 18, 13: 27, 14: "GND", 15: 22, 16: 23, 17: "3V3", 18: 24, 19: 10, 20: "GND",
    21: 9, 22: 25, 23: 11, 24: 8, 25: "GND", 26: 7, 27: "ID", 28: "ID", 29: 5, 30: "GND",
    31: 6, 32: 12, 33: 13, 34: "GND", 35: 19, 36: 16, 37: 26, 38: 20, 39: "GND", 40: 21,
}

SAFETY = [
    "Take the **blue HAT** off the GPIO pins before you change any wires. Put it back on when you're done.",
    "**Don't turn the Pi off** to change wires: you'd lose your progress.",
    "Always put a **330Ω resistor** in series with an LED.",
    "**Never** connect a 5V pin to a GPIO pin. The distance sensor's ECHO wire goes through its two resistors.",
    "No motors straight from the GPIO pins.",
    "Not sure? Ask your teacher to check your circuit before you put the HAT back on.",
]
HAT_FIX = "Take the blue HAT off, fix the wiring, put the HAT back on, then try again."


def on_real_pi() -> bool:
    """True on a Raspberry Pi (set PIPATH_FORCE_SIM=1 to pretend otherwise)."""
    if os.environ.get("PIPATH_FORCE_SIM"):
        return False
    try:
        return "Raspberry Pi" in Path("/proc/device-tree/model").read_text(errors="ignore")
    except OSError:
        return False


def mode_env(mode: str) -> dict:
    return dict(SIM_ENV) if mode == "sim" else {}


CAMERA_KINDS = {"sim": "Simulated", "usb": "USB", "ribbon": "Ribbon"}
SIM_OBJECTS = [("face", "Face"), ("ball", "Ball"), ("box", "Box"), ("nothing", "Empty")]


def guess_camera() -> str:
    """A sensible first choice: a plugged-in USB webcam, else the ribbon camera on a Pi, else the Simulator."""
    drivers = {os.path.basename(os.path.realpath(node / "device" / "driver"))
               for node in Path("/sys/class/video4linux").glob("video*")}
    if "uvcvideo" in drivers:
        return "usb"
    if drivers & {"unicam", "rp1-cfe", "bcm2835-unicam"}:      # a camera on the ribbon socket
        return "ribbon"
    return "sim"


def expand_events(events: list | None) -> list[tuple[float, str]]:
    """Turn a step's demo_events into timed shim commands.

    "1.5 press 23" / "1.8 release 23"     one command at 1.5 s / 1.8 s
    "2 tap 23"                            press, then release 0.2 s later
    "1 tap 23 every 0.8 until 30"         keep tapping (for games with random waits)
    "1.5 distance 26 15"                  the distance sensor on echo GPIO26 sees something 15 cm away
    """
    out: list[tuple[float, str]] = []
    for ev in events or []:
        w = str(ev).split()
        t, action = float(w[0]), w[1]
        args = w[2:w.index("every")] if "every" in w else w[2:]       # "distance 26 15": a pin and a value
        pin = args[0]
        every = float(w[w.index("every") + 1]) if "every" in w else None
        until = float(w[w.index("until") + 1]) if "until" in w else t
        times = [t] if not every else [t + i * every for i in range(int((until - t) / every) + 1)]
        for x in times:
            if action == "tap":
                out += [(x, f"press {pin}"), (x + 0.2, f"release {pin}")]
            else:
                out.append((x, " ".join([action, *args])))
    return sorted(out)


def wiring_parts(lesson: dict) -> list[dict]:
    """The [[wiring]] rows that describe a part on a pin (rows without a kind are tips)."""
    parts = []
    for row in lesson.get("wiring", []):
        kind = row.get("kind")
        pins = row.get("pins") or ([row["pin"]] if "pin" in row else [])
        if kind and pins:
            parts.append({"kind": kind, "pins": [int(p) for p in pins], "label": row.get("part", kind),
                          "colour": row.get("colour", "red")})
    return parts


def wiring_check_program(parts: list[dict]) -> str:
    """A tiny program that tests each part in turn and prints ✓ / ✗ lines the app can read."""
    lines = [
        "from gpiozero import LED, Button, Buzzer, MotionSensor, RGBLED, DistanceSensor, Servo",
        "from time import sleep",
        "",
        'print("Checking your wiring, one part at a time.")',
    ]
    for p in parts:
        name, pins, k = re.sub(r'["\\{}]', "", str(p["label"])), p["pins"], p["kind"]   # safe inside "..."
        pin = pins[0]
        if k == "led":
            lines += [f'print("Watch the {name} (GPIO{pin}): it should blink 3 times.")',
                      f"d = LED({pin})", "d.blink(0.3, 0.3, n=3, background=False)", "d.close()",
                      f'print("• {name} (GPIO{pin}) done. Did it blink? If not, check its long leg and resistor.")']
        elif k == "servo":
            lines += [f'print("Clear the gate before testing {name}.")',
                      f"d = Servo({pin}, initial_value=None)",
                      "for position in (-0.5, 0, 0.5, 0):",
                      "    d.value = position", "    sleep(0.7)",
                      "d.detach()", "d.close()",
                      f'print("• {name} done. Did the arm move both ways and return to centre?")']
        elif k == "rgbled":
            lines += [f'print("Watch the {name}: red, then green, then blue.")',
                      f"d = RGBLED({pins[0]}, {pins[1]}, {pins[2]})",
                      "for c in [(1, 0, 0), (0, 1, 0), (0, 0, 1)]:", "    d.color = c", "    sleep(0.6)",
                      "d.close()", f'print("• {name} done. Did you see all three colours?")']
        elif k == "buzzer":
            lines += [f'print("Listen to the {name} (GPIO{pin}): 3 beeps.")',
                      f"d = Buzzer({pin})", "d.beep(0.1, 0.2, n=3, background=False)", "d.close()",
                      f'print("• {name} (GPIO{pin}) done. Did you hear it? If not, check + goes to GPIO{pin}.")']
        elif k in ("button", "switch"):
            lines += [f"d = Button({pin})", f'print("Press the {name} (GPIO{pin}) now...")',
                      "ok = d.wait_for_press(timeout=10)", "d.close()",
                      f'print("✓ {name} (GPIO{pin}) works!" if ok else '
                      f'"✗ No press from the {name} (GPIO{pin}). Check its legs cross the middle gap.")']
        elif k == "pir":
            lines += [f"d = MotionSensor({pin})",
                      f'print("Wave your hand in front of the {name} (GPIO{pin})...")',
                      "ok = d.wait_for_motion(timeout=20)", "d.close()",
                      f'print("✓ {name} (GPIO{pin}) works!" if ok else '
                      f'"✗ No motion from the {name} (GPIO{pin}). Give it a minute to warm up, then check VCC, OUT and GND.")']
        elif k == "distance":
            echo, trig = pins[0], pins[1]
            lines += [f"d = DistanceSensor(echo={echo}, trigger={trig})",
                      f'print("Hold your hand about 10 cm in front of the {name} (GPIO{echo})...")',
                      "seen, ok = 1.0, False",
                      "for _ in range(100):          # up to 20 seconds",
                      "    seen = d.distance",
                      "    if seen < 0.2:",
                      "        ok = True",
                      "        break",
                      "    sleep(0.2)",
                      "d.close()",
                      f'print(f"✓ {name} (GPIO{echo}) works! It saw your hand {{round(seen * 100)}} cm away." if ok else '
                      f'"✗ The {name} (GPIO{echo}) didn\'t see your hand. Check TRIG goes to GPIO{trig}, ECHO goes '
                      f'through the resistors to GPIO{echo}, and VCC is on 5V.")']
    lines.append('print("Wiring check finished.")')
    return "\n".join(lines) + "\n"
