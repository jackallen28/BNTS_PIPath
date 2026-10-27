import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from wastepath.camera import Camera, usb_cameras

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
            camera=Camera(0)
            deadline=time.monotonic()+1
            while camera.read()[1].startswith('Connecting') and time.monotonic()<deadline:
                time.sleep(.01)
            frame,error=camera.read()
            camera.close(); camera.thread.join(1)
        self.assertIsNone(frame)
        self.assertIn('unavailable',error)
        self.assertTrue(cap.released)
        self.assertFalse(camera.thread.is_alive())

    def test_finds_usb_webcam_among_pi5_video_devices(self):
        with tempfile.TemporaryDirectory() as root:
            def node(n,device,index):
                target=Path(root)/'devices'/device; target.mkdir(parents=True,exist_ok=True)
                v=Path(root)/'class'/f'video{n}'; v.mkdir(parents=True)
                os.symlink(target,v/'device'); (v/'index').write_text(f'{index}\n')
            node(0,'platform/1f00110000.csi/rp1-cfe',0)       # ribbon camera interface
            node(19,'platform/rpi-hevc-dec',0)
            node(20,'platform/1000880000.pisp_be',0)
            node(8,'platform/xhci-hcd.0/usb1/1-1/1-1:1.0',0)  # the webcam's picture device
            node(9,'platform/xhci-hcd.0/usb1/1-1/1-1:1.0',1)  # its metadata device
            node(10,'platform/xhci-hcd.1/usb3/3-1/3-1:1.0',0) # a second webcam
            self.assertEqual(usb_cameras(Path(root)/'class'),[8,10])
            self.assertEqual(usb_cameras(Path(root)/'missing'),[])

    def test_auto_camera_waits_for_a_webcam_and_uses_the_one_found(self):
        opened=[]
        class Live:
            def set(self,*args): pass
            def read(self):
                import numpy as np
                return True,np.zeros((480,640,3),np.uint8)
            def release(self): pass
        found=[[],[3]]
        with patch('wastepath.camera.usb_cameras',side_effect=lambda:found.pop(0) if len(found)>1 else found[0]), \
             patch('wastepath.camera.cv2.VideoCapture',side_effect=lambda i,*a:opened.append(i) or Live()):
            camera=Camera()
            try:
                deadline=time.monotonic()+1
                while 'No USB webcam' not in camera.read()[1] and time.monotonic()<deadline: time.sleep(.01)
                self.assertIn('No USB webcam',camera.read()[1])
                self.assertEqual(opened,[])
                deadline=time.monotonic()+4
                while camera.read()[0] is None and time.monotonic()<deadline: time.sleep(.02)
                self.assertIsNotNone(camera.read()[0])
                self.assertEqual(opened,[3])
            finally:
                camera.close(); camera.thread.join(3)

if __name__=='__main__': unittest.main()
