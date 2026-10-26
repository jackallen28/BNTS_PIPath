"""Camera reads run off the Tk thread. Only the newest frame is retained."""
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
    elif kind == "People / hands / other":
        cv2.rectangle(frame,(125,200),(340+x,270),(100,160,210),-1)
    elif kind == "Unknown item":
        cv2.circle(frame,(320,240),65,(160,40,150),-1)
    elif kind == "Person outside area":
        cv2.rectangle(frame,(0,0),(95,479),(100,160,210),-1)
    return frame


class Camera:
    def __init__(self, index=0, demo=False):
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
                        cap = cv2.VideoCapture(self.index, cv2.CAP_V4L2)
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
                    frame = cv2.resize(frame,(640,480))
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
