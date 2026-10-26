import time
import unittest
from unittest.mock import patch
from wastepath.camera import Camera

class CameraTests(unittest.TestCase):
    def test_demo_delivers_fresh_frames_and_stops(self):
        camera=Camera(demo=True)
        try:
            deadline=time.monotonic()+2
            frame=None
            while frame is None and time.monotonic()<deadline:
                frame,error=camera.read(); time.sleep(.02)
            self.assertIsNotNone(frame)
            self.assertEqual(frame[2].shape,(480,640,3))
            self.assertLess(time.monotonic()-frame[1],1)
            camera.kind="Waste"
            seq=frame[0]
            while time.monotonic()<deadline:
                frame,_=camera.read()
                if frame[0]>seq: break
                time.sleep(.02)
            self.assertGreater(frame[0],seq)
        finally:
            camera.close(); camera.thread.join(1)
        self.assertFalse(camera.thread.is_alive())

    def test_missing_camera_withdraws_frame_and_can_close_during_retry(self):
        class Missing:
            def set(self,*args): pass
            def read(self): return False,None
            def release(self): self.released=True
        cap=Missing()
        with patch('wastepath.camera.cv2.VideoCapture',return_value=cap):
            camera=Camera()
            deadline=time.monotonic()+1
            while camera.read()[1].startswith('Connecting') and time.monotonic()<deadline:
                time.sleep(.01)
            frame,error=camera.read()
            camera.close(); camera.thread.join(1)
        self.assertIsNone(frame)
        self.assertIn('unavailable',error)
        self.assertTrue(cap.released)
        self.assertFalse(camera.thread.is_alive())

if __name__=='__main__': unittest.main()
