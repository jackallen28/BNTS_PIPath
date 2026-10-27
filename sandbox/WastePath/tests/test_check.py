"""The --check readiness report, with fake GPIO and camera."""
import sys
import types
import unittest
from unittest.mock import patch
import numpy as np
from wastepath import check

class FakeFactory:
    chip=4
    def close(self): self.closed=True

class FakeCap:
    def __init__(self,frames): self.frames=list(frames)
    def set(self,*a): pass
    def read(self): return (True,self.frames.pop(0)) if self.frames else (False,None)
    def release(self): pass

class CheckTests(unittest.TestCase):
    def report(self,**patches):
        lines=[]
        with patch.multiple(check,_os_name=lambda:"Raspberry Pi OS",**patches):
            code=check.run(out=lines.append)
        return code,"\n".join(lines)

    def test_ready_pi(self):
        lgpio_pins=types.SimpleNamespace(LGPIOFactory=FakeFactory)
        with patch.dict(sys.modules,{'gpiozero.pins.lgpio':lgpio_pins}), \
             patch('wastepath.camera.usb_cameras',return_value=[8]), \
             patch('cv2.VideoCapture',return_value=FakeCap([np.zeros((480,640,3),np.uint8)])):
            code,text=self.report()
        self.assertEqual(code,0,text)
        self.assertIn("GPIO chip 4",text)
        self.assertIn("/dev/video8 gives 640×480",text)
        self.assertIn("Ready to go",text)

    def test_reports_each_problem_with_a_fix(self):
        def no_gpio(): raise RuntimeError("Cannot open gpiochip")
        with patch('wastepath.camera.usb_cameras',return_value=[]):
            code,text=self.report(check_gpio=no_gpio)
        self.assertEqual(code,1)
        self.assertIn("✗ GPIO: Cannot open gpiochip",text)
        self.assertIn("✗ Camera: no USB webcam found",text)
        self.assertIn("2 problem(s)",text)

    def test_camera_that_sends_no_picture(self):
        with patch('wastepath.camera.usb_cameras',return_value=[0]), \
             patch('cv2.VideoCapture',return_value=FakeCap([])):
            with self.assertRaisesRegex(RuntimeError,"sent no picture"): check.check_camera()

if __name__=='__main__': unittest.main()
