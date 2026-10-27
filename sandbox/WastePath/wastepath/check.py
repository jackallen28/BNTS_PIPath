"""`main.py --check`: is this Pi ready for WastePath? Never moves an output."""
from pathlib import Path
import platform
import sys


def _model():
    try:
        return Path("/proc/device-tree/model").read_text().strip("\x00\n ")
    except OSError:
        return "not a Raspberry Pi"


def _os_name():
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip('"')
    except OSError:
        pass
    return platform.platform()


def check_libraries():
    import tkinter
    import cv2
    import numpy
    import PIL
    from PIL import ImageTk  # noqa: F401  (python3-pil.imagetk)
    import gpiozero  # noqa: F401
    return (f"Python {platform.python_version()}, Tk {tkinter.TkVersion}, OpenCV {cv2.__version__}, "
            f"NumPy {numpy.__version__}, Pillow {PIL.__version__}, gpiozero")


def check_gpio():
    # Opening the GPIO chip is enough: no pin is claimed or changed.
    from gpiozero.pins.lgpio import LGPIOFactory
    factory = LGPIOFactory()
    try:
        return f"lgpio can use GPIO chip {factory.chip}"
    finally:
        factory.close()


def check_camera(index=None):
    import cv2
    from .camera import usb_cameras
    if index is None:
        found = usb_cameras()
        if not found:
            raise RuntimeError("no USB webcam found. Plug one in and check again")
        index = found[0]
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        for _ in range(10):  # the first frames can be blank while the camera wakes
            ok, frame = cap.read()
            if ok and frame is not None:
                return f"/dev/video{index} gives {frame.shape[1]}×{frame.shape[0]} pictures"
        raise RuntimeError(f"/dev/video{index} opened but sent no picture. Is another program using it?")
    finally:
        cap.release()


def run(camera=None, out=print):
    out(f"WastePath check on {_model()} ({_os_name()})")
    problems = 0
    for name, test, fix in (
        ("Libraries", check_libraries, "run: bash install.sh"),
        ("GPIO", check_gpio, "use Raspberry Pi OS on a Pi; your user must be in the gpio group"),
        ("Camera", lambda: check_camera(camera), "try another USB port, or --camera N with a number from: ls /dev/video*"),
    ):
        try:
            out(f"  ✓ {name}: {test()}")
        except Exception as exc:
            problems += 1
            out(f"  ✗ {name}: {exc}\n      Fix: {fix}")
    out("Ready to go." if not problems else f"{problems} problem(s) to fix first.")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(run())
