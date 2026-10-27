"""Configurable indicator outputs, isolated from the classifier and Tk.

A fresh accepted label activates one category's rule; every other rule rests.
Real GPIO is explicitly armed for this process only. The watchdog does not depend
on Tk callbacks and disarms if decision updates stop arriving.
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
    active_angle: float = 90
    rest_angle: float = 0


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
        if rule.kind != "off":
            if rule.pin in pins:
                raise ValueError("Each enabled output needs a different BCM pin")
            pins.add(rule.pin)
        for angle in (rule.active_angle, rule.rest_angle):
            if type(angle) not in (int, float) or not math.isfinite(angle) or not 0 <= angle <= 180:
                raise ValueError("Servo angles must be finite numbers from 0 to 180 degrees")
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


class Controller:
    WATCHDOG_SECONDS = 1.5

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
        self._last_update = None
        self._closed = False
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._watchdog = threading.Thread(target=self._watchdog_loop, daemon=True, name="wastepath-gpio-watchdog")
        self._watchdog.start()

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
                        self._devices[rule.label] = factory.AngularServo(
                            rule.pin, min_angle=0, max_angle=180,
                            initial_angle=rule.rest_angle,
                            min_pulse_width=.001, max_pulse_width=.002,
                            frame_width=.02,
                        )
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
            device.angle = rule.active_angle if active else rule.rest_angle

    def _release_locked(self):
        self._rejected=False
        self._applied_rejected=False
        self.armed = False
        errors = []
        for rule in self.config.rules:
            device = self._devices.get(rule.label)
            if device is None:
                continue
            try:
                if rule.kind == "led":
                    device.off()
                elif rule.kind == "servo":
                    device.angle = rule.rest_angle
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
            if self.armed and self._last_update is not None and self.clock() - self._last_update > self.WATCHDOG_SECONDS:
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
        if threading.current_thread() is not self._watchdog:
            self._watchdog.join(timeout=1)
