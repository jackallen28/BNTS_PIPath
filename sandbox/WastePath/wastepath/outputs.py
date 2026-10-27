"""Configurable indicator outputs, isolated from the classifier and Tk.

A fresh accepted label activates one category's rule; every other rule rests.
Real GPIO is explicitly armed for this process only. The watchdog does not depend
on Tk callbacks and disarms if decision updates stop arriving.

The lid servo moves like the BNTS Arduino smart bin: it opens at once, then
closes by sweeping 1° every 15 ms until the lid's closed button presses, holds
for 0.3 s and goes limp, so it doesn't buzz or push against the lid.
"""
from dataclasses import asdict, dataclass
import copy
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time


@dataclass
class OutputRule:
    label: int
    kind: str = "off"
    pin: int = 17
    active_angle: float = 90   # servo: lid open
    rest_angle: float = 0      # servo: lid closed
    button_pin: int = 0        # servo: closed button (pressed when the lid is shut); 0 = none


@dataclass
class OutputConfig:
    rules: list[OutputRule]


def default_config():
    return OutputConfig([OutputRule(0, "led", 17), OutputRule(1, "servo", 18)])


def validate_config(config):
    if not isinstance(config, OutputConfig) or not isinstance(config.rules, list):
        raise ValueError("Output settings must contain a list of rules")
    if len(config.rules) > 2:
        raise ValueError("Use at most one rule for each detected category")
    labels, pins = set(), set()
    for rule in config.rules:
        if not isinstance(rule, OutputRule):
            raise ValueError("Invalid output rule")
        if type(rule.label) is not int or rule.label not in (0, 1):
            raise ValueError("Only Waste and Recycling can activate an output")
        if rule.label in labels:
            raise ValueError("Each category can have only one output rule")
        labels.add(rule.label)
        if rule.kind not in ("off", "led", "servo"):
            raise ValueError("Choose Off, LED or Servo")
        if type(rule.pin) is not int or not 2 <= rule.pin <= 27:
            raise ValueError("Use a BCM GPIO number from 2 to 27, not a physical pin number")
        if type(rule.button_pin) is not int or not (rule.button_pin == 0 or 2 <= rule.button_pin <= 27):
            raise ValueError("Use a BCM GPIO number from 2 to 27 for the closed button, or none")
        if rule.kind != "off":
            used = [rule.pin] + ([rule.button_pin] if rule.kind == "servo" and rule.button_pin else [])
            if any(pin in pins for pin in used) or len(set(used)) < len(used):
                raise ValueError("Each enabled output and button needs a different BCM pin")
            pins.update(used)
        for angle in (rule.active_angle, rule.rest_angle):
            if type(angle) not in (int, float) or not math.isfinite(angle) or not 0 <= angle <= 180:
                raise ValueError("Servo angles must be finite numbers from 0 to 180 degrees")
        if rule.kind == "servo" and rule.active_angle == rule.rest_angle:
            raise ValueError("The open and closed servo angles must be different")
    return config


def save_config(path, config):
    validate_config(config)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"version": 1, "rules": [asdict(r) for r in config.rules]}, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_config(path):
    path = Path(path)
    if path.stat().st_size > 32_768:
        raise ValueError("GPIO settings file is too large")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("rules"), list):
            raise ValueError("Unsupported GPIO settings file")
        if set(data) != {"version", "rules"}:
            raise ValueError("Unsupported GPIO settings fields")
        return validate_config(OutputConfig([OutputRule(**r) for r in data["rules"]]))
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid GPIO settings file") from exc


class ServoDriver:
    """One lid servo, run by its own thread like the Arduino bin's updateLid().

    States: "open" (held open), "closing" (sweeping towards closed), "settling"
    (holding closed for a moment) and "closed" (limp: no pulses, no buzzing).
    `position` is the last angle sent; `found` is where the closed button pressed.
    """
    STEP_SECONDS = .015       # one degree every 15 ms, as in the Arduino bin
    SETTLE_SECONDS = .3       # hold the closed position, then go limp
    RELEASE_SECONDS = .4      # after opening, the closed button should have let go
    HOLD_OPEN_SECONDS = 2.0   # stay open at least this long, so the lid doesn't flap
    OVERTRAVEL = 15           # sweep this far past the saved closed angle looking for the button

    def __init__(self, servo, open_angle, closed_angle, button=None, home=True):
        self.servo, self.button = servo, button
        self.open_angle, self.closed_angle = float(open_angle), float(closed_angle)
        self.direction = 1 if closed_angle > open_angle else -1
        self.state = "closed"
        self.position = self.closed_angle
        self.found = None
        self.fault = ""
        self.error = ""
        self._want_open = False
        self._releasing = False
        self._limit = self.closed_angle
        self._homing = False
        self._pressed_at = None
        self._since = self._opened_at = time.monotonic()
        self._release_checked = True
        self._lock = threading.RLock()
        self._stop = threading.Event()
        if home:
            if self.pressed():
                self.found = self.position   # already shut: stay limp
            elif button is not None:
                self._start_closing(self.open_angle, self._sweep_limit())
            else:
                self._write(self.closed_angle)
                self._enter("settling")
        self._thread = threading.Thread(target=self._run, daemon=True, name="wastepath-servo")
        self._thread.start()

    # ---- requests (any thread) ----
    def pressed(self):
        return self.button is not None and bool(self.button.value)

    def open(self, angle=None):
        with self._lock:
            angle = self.open_angle if angle is None else float(angle)
            self._want_open = True
            if self.state != "open" or self.position != angle:
                self._write(angle)
                self._enter("open")
                self._opened_at = self._since
                self._release_checked = False

    def close(self):
        with self._lock:
            self._want_open = False

    def home(self, start, direction):
        """Calibration: lift the lid to `start`, then sweep towards 0° or 180°
        until the button presses (like the Arduino bin at power-up)."""
        with self._lock:
            self.direction = 1 if direction > 0 else -1
            self.found = None
            self.fault = ""
            self._want_open = False
            self._homing = True
            self.closed_angle = 180.0 if self.direction > 0 else 0.0   # no press: stop at the end
            self._write(float(start))
            self._enter("lifting")
            return True

    def release(self):
        """Close the lid (no waiting while open), then go limp and free the pins."""
        with self._lock:
            self._want_open = False
            self._releasing = True
            if self.state == "open":
                self._opened_at = -1e9

    def join(self, timeout=None):
        self._thread.join(timeout)
        return not self._thread.is_alive()

    @property
    def busy(self):
        return self._thread.is_alive()

    # ---- the worker ----
    def _sweep_limit(self):
        if self.button is None:
            return self.closed_angle
        return min(180.0, max(0.0, self.closed_angle + self.direction * self.OVERTRAVEL))

    def _start_closing(self, start, limit, homing=False):
        self._limit = limit
        self._homing = homing
        self._pressed_at = None
        self._write(start)
        self._enter("closing")

    def _enter(self, state):
        self.state = state
        self._since = time.monotonic()

    def _write(self, angle):
        if angle is not None:
            self.position = min(180.0, max(0.0, float(angle)))
            self.servo.angle = self.position
        else:
            self.servo.angle = None   # stop the pulses: the servo goes limp

    def _step(self, now):
        if self.state == "lifting":
            # Give the lid time to lift off the button before sweeping closed.
            if now - self._since >= self.RELEASE_SECONDS:
                if self.pressed():
                    self.fault = (f"The button is still pressed at {self.position:g}°. Is the button stuck, "
                                  "or does the lid close the other way?")
                    self._write(None)
                    self._enter("closed")
                else:
                    self._start_closing(self.position, self.closed_angle, homing=True)
        elif self.state == "open":
            if not self._release_checked and now - self._opened_at >= self.RELEASE_SECONDS:
                self._release_checked = True
                if self.pressed():
                    self.fault = "The closed button is still pressed after opening. Is the lid stuck?"
            if not self._want_open and now - self._opened_at >= self.HOLD_OPEN_SECONDS:
                self._start_closing(self.position, self._sweep_limit())
        elif self.state == "closing":
            if self.pressed():
                if self._pressed_at is None:
                    self._pressed_at = self.found = self.position
                    self.fault = ""
                # A saved closed angle a little past the press point ("close 5° more").
                remaining = (self.closed_angle - self.position) * self.direction
                if (not self._homing and remaining > 0 and
                        (self.closed_angle - self._pressed_at) * self.direction <= self.OVERTRAVEL):
                    self._write(self.position + self.direction * min(1.0, remaining))
                else:
                    self._enter("settling")
            elif (self.position - self._limit) * self.direction >= 0:
                if self.button is not None:
                    # Like the Arduino's FALLBACK_CLOSED_ANGLE: rest at the saved angle.
                    self.fault = "The closed button didn't press. Check its wires, or set up the bin again."
                    self._write(self.closed_angle)
                self._enter("settling")
            else:
                self._write(self.position + self.direction)
        elif self.state == "settling":
            if now - self._since >= self.SETTLE_SECONDS:
                self._write(None)
                self._enter("closed")
        elif self._releasing:
            return True
        return False

    def _run(self):
        try:
            while not self._stop.wait(self.STEP_SECONDS):
                with self._lock:
                    if self._step(time.monotonic()):
                        break
        except Exception as exc:
            self.error = f"servo BCM{getattr(self.servo, 'pin', '?')} failed: {exc}"
        finally:
            if self._releasing or self.error:
                self._free()

    def _free(self):
        for device in (self.servo, self.button):
            if device is None:
                continue
            try:
                if device is self.servo:
                    device.angle = None
            except Exception:
                pass
            try:
                device.close()
            except Exception as exc:
                self.error = self.error or f"release failed: {exc}"

    def stop_now(self):
        """Stop moving, go limp and free the pins straight away (app closing, faults)."""
        self._stop.set()
        with self._lock:
            self._releasing = True
        if threading.current_thread() is not self._thread:
            self._thread.join(1)


class Controller:
    WATCHDOG_SECONDS = 1.5
    LID_CLOSE_SECONDS = 5

    def __init__(self, config=None, factory=None, clock=time.monotonic):
        self.config = copy.deepcopy(validate_config(config if config is not None else default_config()))
        self.factory = factory
        self.clock = clock
        self.armed = False
        self.error = ""
        self._label = None
        self._rejected = False
        self._applied_label = None
        self._applied_rejected = False
        self._devices = {}
        self._closing = []   # lids still closing after a stop; their pins are not free yet
        self._last_update = None
        self._closed = False
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._watchdog = threading.Thread(target=self._watchdog_loop, daemon=True, name="wastepath-gpio-watchdog")
        self._watchdog.start()

    @property
    def lid_closing(self):
        self._closing = [d for d in self._closing if d.busy]
        return bool(self._closing)

    @property
    def state_text(self):
        with self._lock:
            prefix = "Real GPIO" if self.armed else "Simulation"
            if self.error:
                return f"Outputs stopped: {self.error}"
            states = []
            for rule in self.config.rules:
                name = "Waste" if rule.label == 0 else "Recycling"
                active = self._label == rule.label or (self._rejected and rule.kind=="led")
                if rule.kind == "off":
                    states.append(f"{name}: Off")
                elif rule.kind == "led":
                    states.append(f"{name}: LED BCM{rule.pin} {'FLASHING' if active else 'off'}")
                elif self.armed and isinstance(self._devices.get(rule.label), ServoDriver):
                    lid = self._devices[rule.label]
                    text = f"{name}: servo BCM{rule.pin} {lid.state} {lid.position:g}°"
                    if lid.fault:
                        text += f" ⚠ {lid.fault}"
                    states.append(text)
                else:
                    angle = rule.active_angle if active else rule.rest_angle
                    states.append(f"{name}: servo BCM{rule.pin} {angle:g}°")
            return prefix + " | " + ("; ".join(states) or "No outputs configured")

    def configure(self, config):
        with self._lock:
            self._label = None
            cleanup = self._release_locked()
            self.error = cleanup
            try:
                self.config = copy.deepcopy(validate_config(config))
            except ValueError as exc:
                self.error = str(exc)
                raise

    def arm(self):
        with self._lock:
            if self._closed:
                self.error = "The output controller is closed"
                return False
            if self.armed:
                return True
            if self.lid_closing:
                self.error = "Wait a moment: the lid is still closing"
                return False
            self.error = ""
            self._label = None
            self._applied_label = None
            if not any(r.kind != "off" for r in self.config.rules):
                self.error = "Configure an LED or servo before enabling real GPIO"
                return False
            try:
                validate_config(self.config)
                factory = self.factory
                if factory is None:
                    import gpiozero
                    factory = gpiozero
                for rule in self.config.rules:
                    if rule.kind == "led":
                        self._devices[rule.label] = factory.LED(rule.pin, initial_value=False)
                    elif rule.kind == "servo":
                        self._devices[rule.label] = make_lid(factory, rule)
                self._last_update = self.clock()
                self.armed = True
                return True
            except Exception as exc:
                self._fault_locked(f"GPIO could not start: {exc}")
                return False

    def disarm(self):
        with self._lock:
            self._label = None
            cleanup = self._release_locked()
            if cleanup:
                self.error = cleanup

    def update(self, label, rejected=False):
        with self._lock:
            if label is not None and (type(label) is not int or label not in (0, 1)):
                self._fault_locked("Invalid detection: no output can be activated")
                return
            if type(rejected) is not bool:
                self._fault_locked("Invalid rejection state")
                return
            if rejected: label=None
            if self._closed or self.error:
                self._label = None
                return
            self._last_update = self.clock()
            self._label = label
            self._rejected = rejected
            if not self.armed or (label == self._applied_label and rejected == self._applied_rejected):
                return
            try:
                # Withdraw the previous category before activating the next one.
                for rule in self.config.rules:
                    if not (rule.label==label or (rejected and rule.kind=="led")):
                        self._write(rule, False)
                for rule in self.config.rules:
                    if rule.label==label or (rejected and rule.kind=="led"):
                        self._write(rule, True)
                self._applied_label = label
                self._applied_rejected = rejected
            except Exception as exc:
                self._fault_locked(f"GPIO write failed: {exc}")

    def neutral(self):
        self.update(None)

    def _write(self, rule, active):
        if rule.kind == "off":
            return
        device = self._devices[rule.label]
        if rule.kind == "led":
            device.blink(on_time=.25,off_time=.25,background=True) if active else device.off()
        else:
            device.open() if active else device.close()

    def _release_locked(self):
        self._rejected=False
        self._applied_rejected=False
        self.armed = False
        errors = []
        for rule in self.config.rules:
            device = self._devices.get(rule.label)
            if device is None:
                continue
            if isinstance(device, ServoDriver):
                # The lid closes gently in the background, then frees its pins.
                if device.error:
                    errors.append(device.error)
                device.release()
                self._closing.append(device)
                continue
            try:
                device.off()
            except Exception as exc:
                errors.append(f"BCM{rule.pin} rest failed: {exc}")
            try:
                device.close()
            except Exception as exc:
                errors.append(f"BCM{rule.pin} release failed: {exc}")
        self._devices = {}
        self._applied_label = None
        self._last_update = None
        return "; ".join(errors)

    def _fault_locked(self, reason):
        self._label = None
        cleanup = self._release_locked()
        self.error = reason + (f"; {cleanup}" if cleanup else "")

    def check_watchdog(self):
        with self._lock:
            if not self.armed:
                return False
            for device in self._devices.values():
                if isinstance(device, ServoDriver) and device.error:
                    self._fault_locked(device.error)
                    return True
            if self._last_update is not None and self.clock() - self._last_update > self.WATCHDOG_SECONDS:
                self._fault_locked("No fresh decisions for 1.5 seconds; enable real GPIO again")
                return True
            return False

    def _watchdog_loop(self):
        while not self._stop.wait(.1):
            self.check_watchdog()

    def close(self):
        self._stop.set()
        with self._lock:
            self._closed = True
            self._label = None
            cleanup = self._release_locked()
            if cleanup:
                self.error = cleanup
        # Let an open lid finish closing before the program ends.
        for lid in list(self._closing):
            if not lid.join(self.LID_CLOSE_SECONDS):
                lid.stop_now()
        if threading.current_thread() is not self._watchdog:
            self._watchdog.join(timeout=1)


def make_lid(factory, rule, home=True):
    """The servo (and its closed button) for one rule, ready to open and close."""
    servo = factory.AngularServo(
        rule.pin, min_angle=0, max_angle=180, initial_angle=None,
        min_pulse_width=.001, max_pulse_width=.002, frame_width=.02,
    )
    button = None
    try:
        if rule.button_pin:
            # Button between the GPIO pin and GND: the Pi's own pull-up, never 5 V.
            button = factory.InputDevice(rule.button_pin, pull_up=True)
        return ServoDriver(servo, rule.active_angle, rule.rest_angle, button, home=home)
    except Exception:
        for device in (button, servo):
            if device is not None:
                try: device.close()
                except Exception: pass
        raise
