"""Camera reads run off the Tk thread. Only the newest frame is retained."""
from pathlib import Path
import threading
import time
import cv2
import numpy as np


def demo_frame(kind="Empty table", variation=0):
    frame = np.full((480,640,3), (75,70,65), np.uint8)
    x = int(variation % 5)*3
    if kind == "Waste":
        pts = np.array([[260+x,180],[365+x,190],[350+x,300],[285+x,285]],np.int32)
        cv2.fillPoly(frame,[pts],(170,80,35))
    elif kind == "Recycling":
        cv2.ellipse(frame,(320+x,240),(45,68),int(variation%5)*4,0,360,(30,150,220),-1)
    elif kind == "Unknown item":
        cv2.circle(frame,(320,240),65,(160,40,150),-1)
    return frame


def normalise_frame(frame):
    # Preserve shapes: the original crops widescreen webcams to 4:3 before resize.
    h,w=frame.shape[:2]
    if w*3>h*4+8:
        cut=(w-h*4//3)//2
        frame=frame[:,cut:w-cut]
    return cv2.resize(frame,(640,480),interpolation=cv2.INTER_AREA)


def usb_cameras(root="/sys/class/video4linux"):
    """Numbers of the USB webcams' picture devices (/dev/videoN), lowest first.

    A Raspberry Pi 5 has its own video devices too (the ribbon-camera
    interface and image processors), so /dev/video0 is not always the webcam.
    """
    found = []
    for node in Path(root).glob("video[0-9]*"):
        try:
            # Each webcam has a picture device (index 0) and a metadata device.
            if "/usb" in str((node / "device").resolve()) and (node / "index").read_text().strip() == "0":
                found.append(int(node.name[5:]))
        except (OSError, ValueError):
            pass
    return sorted(found)


class Camera:
    """index=None finds the USB webcam each time it connects (it may be renumbered)."""
    def __init__(self, index=None, demo=False):
        self.index, self.demo = index, demo
        self.kind = "Empty table"
        self.lock = threading.Lock()
        self.latest = None
        self.error = "Connecting to the camera…"
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        cap = None
        seq = 0
        try:
            while not self.stop_event.is_set():
                frame = None
                if self.demo:
                    frame = demo_frame(self.kind)
                    self.stop_event.wait(.1)
                else:
                    if cap is None:
                        index = self.index
                        if index is None:
                            found = usb_cameras()
                            if not found:
                                with self.lock:
                                    self.latest = None
                                    self.error = "No USB webcam found. Plug one in; it will connect by itself."
                                self.stop_event.wait(2)
                                continue
                            index = found[0]
                        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH,640)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
                        cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        cap.release()
                        cap = None
                        with self.lock:
                            self.latest = None
                            self.error = "Camera unavailable. Reconnect it, or choose another camera number."
                        self.stop_event.wait(2)
                        continue
                    frame = normalise_frame(frame)
                seq += 1
                with self.lock:
                    self.latest = (seq,time.monotonic(),frame)
                    self.error = ""
        except Exception as e:
            with self.lock:
                self.latest = None
                self.error = f"Camera stopped: {e}"
        finally:
            if cap is not None: cap.release()

    def read(self):
        with self.lock:
            return self.latest, self.error

    def close(self):
        self.stop_event.set()
