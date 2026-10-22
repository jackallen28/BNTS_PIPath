"""Runs a student's program so PiPath can show (and poke) its GPIO pins.

    python3 -u pipath/gpio_shim.py <student_file>
    python3 -u pipath/gpio_shim.py --wait        (warm start: see below)

This file runs INSIDE the student's process, never inside the app.

Warm start: on a Pi 3B, starting Python and importing gpiozero takes a second or more. So the
app starts a spare process early with --wait: it imports the modules in PIPATH_PRELOAD, then
waits for one JSON line on the command fd: {"run": file, "cwd": folder, "env": {...}}.

- Simulator mode (GPIOZERO_PIN_FACTORY=mock): pins are pretend. The app can press
  buttons and trigger the motion sensor by sending commands.
- Real Pi mode: pins are real. The shim only reports what the code is doing, so the
  on-screen board mirrors the program next to the real breadboard.

Messages to the app are JSON lines on the fd named in PIPATH_STATE_FD:
    {"t": "devices", "devices": [{"kind": "LED", "pins": [17]}, ...]}
    {"t": "pins", "pins": {"17": 1.0, "23": 0}}     (outputs: brightness 0-1, inputs: 1 = active)
    {"t": "photo", "path": "/full/path/photo.png"}      (sent by pipath_camera)
    {"t": "input"}                                      (the program is waiting in input())
Commands from the app are text lines on the fd named in PIPATH_CMD_FD:
    press 23 / release 23   (activate / deactivate an input, Simulator only)
    distance 26 15          (the distance sensor with echo on GPIO26 sees something 15 cm away, Simulator only)
    show circle             (what the simulated camera can see)

Tracebacks are trimmed so they start in the student's file, and a Stop (SIGTERM)
exits cleanly, so gpiozero switches real LEDs and buzzers off.
"""
from __future__ import annotations

import builtins
import importlib
import importlib.abc
import importlib.machinery
import json
import os
import runpy
import signal
import sys
import threading
import time
import traceback
import warnings
import weakref
from pathlib import Path

HERE = Path(__file__).resolve().parent
TICK = 0.05

_send_lock = threading.Lock()
_state_fd = int(os.environ["PIPATH_STATE_FD"]) if os.environ.get("PIPATH_STATE_FD") else None
_student = ""                # full path of the student's file
_callback_crashed: list = []  # set when an event handler (e.g. when_pressed) crashes
_main_done: list = []         # set when the student's main code has finished (only threads are left)
_devices: list = []          # weakrefs to gpiozero devices, in the order they were made
_groups: list = []           # weakrefs to RGBLEDs (three pins shown as one light)
camera_view = {"object": os.environ.get("PIPATH_CAMERA_OBJECT", "face")}   # what the simulated camera sees
_gz = None                    # the gpiozero module, once the student imports it
_sim_distance: dict[int, float] = {}   # Simulator: echo pin -> what the distance sensor "sees", in metres
MOCK_PIN_CLASSES = {"mockpin": "MockPin", "mockpwmpin": "MockPWMPin"}


def send(msg: dict) -> None:
    """Send one message to the app (ignored when not running inside PiPath)."""
    if _state_fd is None:
        return
    data = (json.dumps(msg, separators=(",", ":")) + "\n").encode()
    with _send_lock:
        try:
            os.write(_state_fd, data)
        except OSError:
            pass


# ---------------------------------------------------------------- watching gpiozero

def _bcm(pin) -> int | None:
    name = getattr(getattr(pin, "info", None), "name", "") or ""
    return int(name[4:]) if name.startswith("GPIO") and name[4:].isdigit() else None


def _patch_gpiozero(gz) -> None:
    """Remember every device the student makes, so the board knows what to draw."""
    global _gz
    _gz = gz
    orig_init = gz.GPIODevice.__init__

    def gpio_init(self, *a, **kw):
        orig_init(self, *a, **kw)
        _devices.append(weakref.ref(self))

    gz.GPIODevice.__init__ = gpio_init

    orig_servo = gz.Servo.__init__

    def servo_init(self, *a, **kw):
        orig_servo(self, *a, **kw)
        _groups.append(weakref.ref(self))

    gz.Servo.__init__ = servo_init

    orig_rgb = gz.RGBLED.__init__

    def rgb_init(self, *a, **kw):
        orig_rgb(self, *a, **kw)
        _groups.append(weakref.ref(self))

    gz.RGBLED.__init__ = rgb_init

    orig_tonal = gz.TonalBuzzer.__init__

    def tonal_init(self, *a, **kw):
        orig_tonal(self, *a, **kw)
        _groups.append(weakref.ref(self))

    gz.TonalBuzzer.__init__ = tonal_init

    # Simulator: mock pins can't send an ultrasonic echo, so the distance comes from the board
    orig_read = gz.DistanceSensor._read

    def distance_read(self):
        from gpiozero.pins.mock import MockFactory
        if not isinstance(self.pin_factory, MockFactory):
            return orig_read(self)
        return min(1.0, _sim_distance.get(_bcm(self.pin), 1.0) / self._max_distance)

    gz.DistanceSensor._read = distance_read
    if _student:              # imported by the student's program (a warm start does this in _run)
        _apply_factory(gz)


def _apply_factory(gz) -> None:
    """Simulator: make the mock pin factory ourselves. Asking gpiozero for it by name makes it
    scan every installed package (twice), which takes seconds on a Pi 3B."""
    if os.environ.get("GPIOZERO_PIN_FACTORY") != "mock" or gz.Device.pin_factory is not None:
        return
    name = MOCK_PIN_CLASSES.get(os.environ.get("GPIOZERO_MOCK_PIN_CLASS", "mockpin").lower())
    if name is None:
        return                  # something unusual: let gpiozero look it up
    try:
        from gpiozero.pins import mock
        gz.Device.pin_factory = mock.MockFactory(pin_class=getattr(mock, name))
    except Exception:
        pass


class _GpiozeroHook(importlib.abc.MetaPathFinder):
    """Patch gpiozero the moment the student imports it (and never import it otherwise)."""

    def find_spec(self, name, path=None, target=None):
        if name != "gpiozero":
            return None
        sys.meta_path.remove(self)
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None or spec.loader is None:
            return spec
        loader = spec.loader
        orig_exec = loader.exec_module

        def exec_module(module):
            orig_exec(module)
            _patch_gpiozero(module)

        loader.exec_module = exec_module
        return spec


def _distance_value(d):
    """A distance sensor's latest reading in metres, without waiting (None until it has one)."""
    q = list(d._queue.queue)
    if not q:
        return None
    q.sort()
    return q[len(q) // 2] * d.max_distance


def _snapshot():
    devs, pins, in_group = [], {}, set()
    triggers, skip = set(), set()
    for ref in list(_devices):
        d = ref()
        if d is not None and not d.closed and isinstance(d, _gz.DistanceSensor) and d._trigger is not None:
            echo, trig = _bcm(d.pin), _bcm(d._trigger.pin)
            if echo is None or trig is None:
                continue
            triggers.add(trig)
            in_group.add(echo)
            devs.append({"kind": "DistanceSensor", "pins": [echo, trig]})
            value = _distance_value(d)
            if value is not None:
                pins[str(echo)] = round(value, 3)
    for ref in list(_groups):
        g = ref()
        if g is None or g.closed:
            continue
        if isinstance(g, _gz.Servo):
            p = _bcm(g.pwm_device.pin)
            if p is not None:
                devs.append({"kind": "Servo", "pins": [p]})
                pins[str(p)] = g.value
                in_group.add(p)
                skip.add(p)
            continue
        if isinstance(g, _gz.TonalBuzzer):     # one pin; "on" while it plays a note
            p = _bcm(g._all[0].pin) if g._all else None
            if p is not None:
                devs.append({"kind": "TonalBuzzer", "pins": [p]})
                pins[str(p)] = 1.0 if g.is_active else 0.0
                in_group.add(p)
                skip.add(p)
            continue
        ps = [_bcm(led.pin) for led in g._leds]
        if None not in ps:
            devs.append({"kind": "RGBLED", "pins": ps})
            in_group.update(ps)
    for ref in list(_devices):
        d = ref()
        if d is None or d.closed:
            continue
        p = _bcm(d.pin)
        if (p is None or p in skip or isinstance(d, _gz.DistanceSensor)
                or (p in triggers and type(d) is _gz.GPIODevice)):
            continue          # distance sensors were reported above (reading is_active would wait)
        try:
            # outputs: how bright / on (honours active_high); inputs: pressed / motion seen
            state = d.value if isinstance(d, _gz.OutputDevice) else d.is_active
        except Exception:
            continue
        pins[str(p)] = round(float(state), 2)
        if p not in in_group:
            devs.append({"kind": type(d).__name__, "pins": [p]})
    return devs, pins


def _reporter() -> None:
    last_devs, last_pins = None, None
    while True:
        time.sleep(TICK)
        try:
            devs, pins = _snapshot()
        except Exception:
            continue
        if devs != last_devs:
            send({"t": "devices", "devices": devs})
            last_devs = devs
        if pins != last_pins:
            send({"t": "pins", "pins": pins})
            last_pins = pins


def _find_device(pin_no: int):
    for ref in list(_devices):
        d = ref()
        if d is not None and not d.closed and _bcm(d.pin) == pin_no:
            return d
    return None


def _run_command(line: bytes) -> None:
    try:
        _command(line.decode("utf-8", "replace").split())
    except SystemExit:                     # sys.exit() in a when_pressed handler: end the program
        os.kill(os.getpid(), signal.SIGTERM)


def _listener(fd: int, buf: bytes = b"") -> None:
    while b"\n" in buf:
        line, buf = buf.split(b"\n", 1)
        _run_command(line)
    while True:
        try:
            chunk = os.read(fd, 1024)
        except OSError:
            return
        if not chunk:
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            _run_command(line)


def _command(words: list[str]) -> None:
    if len(words) == 2 and words[0] == "show":
        camera_view["object"] = words[1]
        return
    if len(words) == 3 and words[0] == "distance" and words[1].isdigit():
        if os.environ.get("GPIOZERO_PIN_FACTORY") == "mock":
            try:
                _sim_distance[int(words[1])] = max(0.02, float(words[2]) / 100)
            except ValueError:
                pass
        return
    if len(words) == 3 and words[0] == "stat" and words[1] in ("temp", "load", "ram"):
        if os.environ.get("GPIOZERO_PIN_FACTORY") == "mock":       # pretend numbers for pipath_computer
            try:
                os.environ[f"PIPATH_SIM_{words[1].upper()}"] = str(float(words[2]))
            except ValueError:
                pass
        return
    if len(words) != 2 or words[0] not in ("press", "release") or not words[1].isdigit():
        return
    if os.environ.get("GPIOZERO_PIN_FACTORY") != "mock":
        return   # never drive real pins from the screen
    d = _find_device(int(words[1]))
    if d is None:
        return
    pin = d.pin
    active_low = getattr(pin, "pull", "") == "up"     # buttons: pressed pulls the pin to GND
    on = words[0] == "press"
    # The student's when_pressed handler runs right here; if it crashes, the error
    # reaches _thread_crashed below, just like a crash in the main program.
    try:
        if on == active_low:
            pin.drive_low()
        else:
            pin.drive_high()
    except Exception:
        if not getattr(d, "closed", False):
            raise                          # a real crash in the student's handler
        # the program closed the button at the same moment it was pressed: nothing to do


# ---------------------------------------------------------------- running the student's file

def _stop(_signum, _frame):
    if _main_done:                         # only the student's threads are left: switch off and go
        try:
            from gpiozero.devices import _shutdown
            _shutdown()
        except Exception:
            pass
        sys.stdout.flush()
        os._exit(1 if _callback_crashed else 0)
    raise SystemExit(0)


def _thread_crashed(args) -> None:
    """An event handler crashed in a background thread: report it and end the program."""
    if args.exc_type is SystemExit:
        return
    _print_student_traceback(args.exc_value, _student)
    _callback_crashed.append(True)
    os.kill(os.getpid(), signal.SIGTERM)   # a real signal also wakes pause() and sleep()


def _print_student_traceback(exc: BaseException, student: str) -> None:
    """Print the traceback starting at the student's file, without this shim or runpy."""
    tb = exc.__traceback__
    while tb is not None and os.path.abspath(tb.tb_frame.f_code.co_filename) != student:
        tb = tb.tb_next
    te = traceback.TracebackException(type(exc), exc, tb)
    sys.stderr.write("".join(te.format()))
    sys.stderr.flush()


def _input(prompt=""):
    """input(), but the app is told first, so it can put the cursor in the answer box."""
    send({"t": "input"})
    return _real_input(prompt)


_real_input = builtins.input


def _setup() -> None:
    """Hooks every run needs. Done before a warm process waits, too."""
    builtins.input = _input
    # gpiozero suggests pigpio for every distance sensor; lgpio is what Pi OS uses, so don't worry students
    warnings.filterwarnings("ignore", message="For more accurate readings")
    sys.path.append(str(HERE / "student_lib"))
    sys.meta_path.insert(0, _GpiozeroHook())
    signal.signal(signal.SIGTERM, _stop)
    threading.excepthook = _thread_crashed
    sys.modules["pipath_shim"] = sys.modules[__name__]


def _run(student: str, cmd_buf: bytes = b"") -> int:
    global _student
    student = _student = os.path.abspath(student)
    sys.argv = [student]
    sys.path[0] = os.path.dirname(student)
    camera_view["object"] = os.environ.get("PIPATH_CAMERA_OBJECT", "face")
    if _gz is not None:                 # gpiozero was preloaded: pick the pin factory now
        _apply_factory(_gz)
    if _state_fd is not None:
        threading.Thread(target=_reporter, daemon=True).start()
    if os.environ.get("PIPATH_CMD_FD"):
        threading.Thread(target=_listener, args=(int(os.environ["PIPATH_CMD_FD"]), cmd_buf), daemon=True).start()
    send({"t": "hello", "mode": "sim" if os.environ.get("GPIOZERO_PIN_FACTORY") == "mock" else "real"})
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and "turtle" not in sys.modules:
        import _headless_turtle          # no screen to draw on: turtle programs still run to the end
        sys.modules["turtle"] = _headless_turtle

    try:
        runpy.run_path(student, run_name="__main__")
    except SystemExit:
        if _callback_crashed:
            return 1
        raise
    except KeyboardInterrupt:
        return 130
    except BaseException as e:   # noqa: BLE001 - every crash is reported, then the app explains it
        _print_student_traceback(e, student)
        return 1
    _main_done.append(True)
    return 0


def _wait() -> int:
    """Warm start: load the slow modules now, then wait to be told which file to run."""
    sys.path[0] = str(HERE / "student_lib")       # never import the app's own modules by mistake
    quiet = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(1), os.dup(2)
    os.dup2(quiet, 1)                              # anything printed while loading isn't the student's
    os.dup2(quiet, 2)
    try:
        for name in filter(None, os.environ.get("PIPATH_PRELOAD", "").split(",")):
            try:
                importlib.import_module(name)
            except Exception:
                pass
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for fd in (quiet, *saved):
            os.close(fd)
    fd = int(os.environ["PIPATH_CMD_FD"])
    buf = b""
    while b"\n" not in buf:
        chunk = os.read(fd, 4096)
        if not chunk:
            return 0                                 # the app closed before we were needed
        buf += chunk
    line, rest = buf.split(b"\n", 1)
    order = json.loads(line)
    os.environ.update({k: str(v) for k, v in order.get("env", {}).items()})
    os.chdir(order.get("cwd") or os.path.dirname(order["run"]))
    return _run(order["run"], rest)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: gpio_shim.py <student_file> | --wait", file=sys.stderr)
        return 2
    _setup()
    if sys.argv[1] == "--wait":
        return _wait()
    return _run(sys.argv[1])


if __name__ == "__main__":
    sys.exit(main())
