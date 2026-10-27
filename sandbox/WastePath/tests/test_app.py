"""Real Tk workflow on a synthetic camera, never a claim of hardware accuracy."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from wastepath.camera import demo_frame
from wastepath.model import LABELS

class FakeCamera:
    def __init__(self,*args):
        self.kind="Empty table"
        self.frame=demo_frame()
        self.seq=0
        self.offline=False
    def read(self):
        if self.offline: return None,"Unplugged"
        self.seq+=1
        return (self.seq,time.monotonic(),self.frame),""
    def close(self): pass

@unittest.skipUnless(os.environ.get("DISPLAY"),"Needs a Tk display")
class WorkshopTests(unittest.TestCase):
    def setUp(self):
        from wastepath.app import App
        self.tmp=tempfile.TemporaryDirectory()
        self.patcher=patch("wastepath.app.Camera",FakeCamera)
        self.patcher.start()
        self.app=App(self.tmp.name,demo=True)
        # Drive ticks deterministically instead of running recurring timers.
        for timer in self.app.tk.call("after","info"):
            self.app.after_cancel(timer)
        self.app.after=lambda *args:None
        self.app.geometry("1024x640")
        self.app.update_idletasks()
        from wastepath.outputs import ServoDriver
        for name,value in (("STEP_SECONDS",.001),("SETTLE_SECONDS",.01),("HOLD_OPEN_SECONDS",0)):
            self.addCleanup(setattr,ServoDriver,name,getattr(ServoDriver,name))
            setattr(ServoDriver,name,value)
    def wait(self,condition,seconds=3):
        deadline=time.monotonic()+seconds
        while not condition() and time.monotonic()<deadline:
            self.app.tick(); time.sleep(.005)
        return condition()
    def tearDown(self):
        self.app.close(); self.patcher.stop(); self.tmp.cleanup()
    def view(self,kind,variation=0):
        self.app.cam.frame=demo_frame(kind,variation)
        for _ in range(8): self.app.tick()
        self.app.update_idletasks()
    def train_workshop(self):
        a=self.app
        self.view("Empty table")
        a.calibrate()
        self.assertFalse(a.calibrated)
        for _ in range(10): a.tick()
        self.assertTrue(a.calibrated)
        a.show_step(1)
        for label,kind in enumerate(LABELS):
            a.label_var.set(kind)
            a.group_var.set("")
            for photo in range(10):
                self.view(kind,photo)
                a.last_capture=0
                a.capture()
        self.assertEqual(len(a.samples),20)
        a.show_step(2); a.train()
        deadline=time.monotonic()+10
        while a.busy and time.monotonic()<deadline:
            a.tick(); time.sleep(.01)
        self.assertFalse(a.busy)
        self.assertIsNotNone(a.model)
        self.assertEqual(len(a.quiz),2)
        self.assertEqual(a.step,4)
        a.show_step(3); a.gate.seconds=0
    def test_teach_train_test_live_and_camera_loss(self):
        a=self.app
        self.train_workshop()
        self.view("Waste")
        self.assertEqual(a.prediction.label,0)
        before=len(a.samples)
        a.last_capture=0; a.record_test(0)
        self.assertEqual(len(a.test_records),1)
        self.assertEqual(len(a.samples),before)
        self.assertEqual(a.test_records[0]['predicted'],0)
        self.view("Unknown item")
        self.assertIsNone(a.prediction.label)
        a.last_capture=0; a.record_test(2)
        self.assertIsNone(a.test_records[-1]['predicted'])
        self.view("Empty table")
        self.assertIsNone(a.prediction.label)
        a.show_step(4)
        self.view("Recycling")
        self.assertEqual(a.prediction.label,1)
        self.assertLessEqual(a.panel.winfo_width(),a.winfo_width())
        capture=os.environ.get("WASTEPATH_TEST_SCREENSHOT")
        if capture:
            subprocess.run(["import","-window",str(a.winfo_id()),capture],check=True)
        self.assertIn("servo BCM18 90",a.outputs.state_text)
        a.cam.offline=True; a.tick()
        self.assertIn("LED BCM17 off",a.outputs.state_text)
        self.assertIn("servo BCM18 0",a.outputs.state_text)
        self.assertIsNone(a.prediction.label)
        self.assertIsNone(a.gate.label)
    def test_restart_needs_table_check_and_training_change_invalidates(self):
        a=self.app
        self.train_workshop()
        a.show_step(1); a.undo()
        self.assertIsNone(a.model)
        self.assertEqual(a.test_records,[])
        a.calibrated=False
        a.show_step(4)
        self.assertEqual(a.step,1)
        # Saved data resumes with calibration disabled, so no stale live prediction.
        from wastepath.app import App
        other=App(self.tmp.name,demo=True)
        try:
            self.assertFalse(other.calibrated)
            self.assertEqual(len(other.samples),19)
            self.assertIsNone(other.model)
        finally: other.close()
    def test_optional_item_names_and_missing_examples_do_not_train(self):
        a=self.app
        self.view("Empty table"); a.calibrate()
        for _ in range(10): a.tick()
        a.show_step(1)
        self.view("Waste"); a.group_var.set(""); a.capture()
        self.assertEqual(len(a.samples),1)
        a.train()
        self.assertFalse(a.busy)
        self.assertIsNone(a.model)

    def test_background_averages_ten_unique_frames_and_aborts_on_disconnect(self):
        import numpy as np
        from wastepath.vision import shrink,to_lab
        a=self.app
        self.view("Empty table"); a.calibrate()
        frames=[]
        for i in range(9):
            a.cam.frame=np.full((480,640,3),70+i,np.uint8)
            frames.append(to_lab(shrink(a.cam.frame)))
            a.tick()
            self.assertFalse(a.calibrated)
        a.cam.frame=np.full((480,640,3),79,np.uint8)
        frames.append(to_lab(shrink(a.cam.frame))); a.tick()
        self.assertTrue(a.calibrated)
        np.testing.assert_allclose(a.background,np.mean(frames,axis=0))
        a.calibrate(); a.cam.offline=True; a.tick()
        self.assertFalse(a.calibrated)
        self.assertIsNone(a.bg_frames)

    def test_old_training_is_preserved_before_full_frame_retraining(self):
        import numpy as np
        a=self.app
        np.savez(a.file,version=[1],features=np.zeros((1,29)),labels=[0],groups=['old'],background=np.zeros((240,320,3)))
        original=a.file.read_bytes()
        a.load_error="Old cropped training"
        self.view("Empty table")
        with patch('wastepath.app.messagebox.askyesno',return_value=True):
            a.calibrate()
        backups=list(Path(self.tmp.name).glob('training-backup-*.npz'))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_bytes(),original)
        for _ in range(10): a.tick()
        self.assertTrue(a.calibrated)
        from wastepath.storage import load
        self.assertEqual(load(a.file)[0],[])

    def test_gpio_settings_validate_persist_and_never_arm_demo(self):
        a=self.app
        a.show_outputs()
        dialog=a.output_dialog
        self.assertIsNotNone(dialog)
        dialog.rows[0]["pin"].set("18")  # conflicts with the Recycling servo
        dialog.apply()
        self.assertIs(a.output_dialog,dialog)
        self.assertIn("different BCM",dialog.message.get())
        dialog.rows[0]["pin"].set("22")
        dialog.rows[1]["active_angle"].set("120")
        dialog.rows[1]["rest_angle"].set("20")
        dialog.apply()
        self.assertIsNone(a.output_dialog)
        self.assertTrue(a.output_file.exists())
        self.assertEqual(a.outputs.config.rules[0].pin,22)
        self.assertEqual(a.outputs.config.rules[1].active_angle,120)
        with patch.object(a.outputs,"arm") as arm:
            a.arm_outputs()
            arm.assert_not_called()
        self.assertIn("cannot enable",a.status.get())
        from wastepath.app import App
        other=App(self.tmp.name,demo=True)
        try:
            self.assertFalse(other.outputs.armed)
            self.assertEqual(other.outputs.config.rules[0].pin,22)
            self.assertEqual(other.outputs.config.rules[1].rest_angle,20)
        finally: other.close()
        screenshot=os.environ.get("WASTEPATH_GPIO_SCREENSHOT")
        if screenshot:
            a.show_outputs(); a.output_dialog.update_idletasks()
            subprocess.run(["import","-window",str(a.output_dialog.winfo_id()),screenshot],check=True)
            a.output_dialog.cancel()

    def test_real_gpio_live_routing_and_stopping_with_mock_hardware(self):
        # Exercise the real controller with gpiozero's PWM-capable mock pins.
        import gpiozero
        from gpiozero.pins.mock import MockFactory, MockPWMPin
        from wastepath.outputs import Controller
        pin_factory=MockFactory(pin_class=MockPWMPin)
        class Factory:
            @staticmethod
            def LED(pin,**kw): return gpiozero.LED(pin,pin_factory=pin_factory,**kw)
            @staticmethod
            def AngularServo(pin,**kw):
                import warnings
                from gpiozero.exc import PWMSoftwareFallback
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore",PWMSoftwareFallback)
                    return gpiozero.AngularServo(pin,pin_factory=pin_factory,**kw)
        a=self.app
        a.outputs.close()
        a.outputs=Controller(factory=Factory)
        self.train_workshop()
        a.demo=False  # Camera remains synthetic; GPIO factory remains a mock.
        self.view("Waste")
        a.arm_outputs()
        self.assertFalse(a.outputs.armed)  # Test must not operate hardware.
        self.assertFalse(pin_factory.pins)
        a.show_step(4)
        self.view("Waste")
        a.arm_outputs()
        self.assertTrue(a.outputs.armed)
        self.assertEqual(pin_factory.pin(17).state,0)
        a.gate.seconds=0
        self.view("Waste")
        self.assertIsNotNone(a.outputs._devices[0]._blink_thread)
        self.view("Recycling")
        self.assertEqual(pin_factory.pin(17).state,0)
        self.assertAlmostEqual(pin_factory.pin(18).state,.075)   # open at 90°
        self.view("Unknown item")
        self.assertIsNotNone(a.outputs._devices[0]._blink_thread)
        lid=a.outputs._devices[1]
        self.assertTrue(self.wait(lambda:lid.state=="closed"))
        self.assertEqual(lid.position,0)
        self.assertEqual(pin_factory.pin(18).state,0)            # closed, then limp
        self.view("Waste")
        self.assertIsNotNone(a.outputs._devices[0]._blink_thread)
        a.show_outputs()
        self.assertFalse(a.outputs.armed)
        self.assertEqual(pin_factory.pin(17).state,0)
        a.output_dialog.cancel()
        a.gate.seconds=0; self.view("Waste")
        a.arm_outputs(); a.gate.seconds=0; self.view("Waste")
        self.assertTrue(a.outputs.armed)
        a.cam.offline=True; a.tick()
        self.assertEqual(pin_factory.pin(17).state,0)
        self.assertTrue(self.wait(lambda:a.outputs._devices[1].state=="closed"))
        a.show_step(1)
        self.assertFalse(a.outputs.armed)
        self.assertEqual(pin_factory.pin(17).state,0)

    def test_take_more_photos_after_ten_and_add_more_from_the_quiz(self):
        a=self.app
        self.train_workshop()
        a.show_step(2)
        a.more_photos("Recycling")
        self.assertEqual((a.step,a.label_var.get()),(1,"Recycling"))
        for photo in range(3):
            self.view("Recycling",photo+3); a.last_capture=0; a.capture()
        self.assertEqual(a.step,1)                  # no jump away while adding photos
        self.assertEqual(sum(s.label==1 for s in a.samples),13)
        self.assertIsNone(a.model)                  # train again to use them
        self.assertIn("Train again",a.status.get())
        a.update()
        self.assertTrue(all(s.thumb is not None for s in a.samples))
        self.assertIn("+3 extra",[a.cards[1].itemcget(i,"text") for i in a.cards[1].find_all() if a.cards[1].type(i)=="text"])
        self.assertIn("Both bins are ready",a.counts.cget("text"))
        a.choose_bin("Waste")
        self.assertEqual(a.label_var.get(),"Waste")
        capture=os.environ.get("WASTEPATH_TEST_SCREENSHOT_TEACH")
        if capture:
            a.update(); subprocess.run(["import","-window",str(a.winfo_id()),capture],check=True)

    def test_bin_setup_finds_closed_sets_open_and_saves(self):
        a=self.app
        self.train_workshop()
        a.show_step(5)
        self.assertEqual(a.step,5)
        a.bin_vars["closes"].set("up")
        a.bin_find()
        self.assertTrue(self.wait(lambda:a.bin.closed_angle is not None))
        self.assertEqual(a.bin.closed_angle,120)
        self.assertIn("Closed at 120",(a.draw_bin(),a.bin_note.cget("text"))[1])
        for _ in range(8): a.bin_open(1)
        self.assertEqual(a.bin.open_angle,80)
        a.bin_test()
        self.assertTrue(self.wait(lambda:a.bin.lid.state=="closed" and a.bin.lid.found==120))
        a.update()
        capture=os.environ.get("WASTEPATH_TEST_SCREENSHOT_BIN")
        if capture:
            a.draw_bin(); a.update(); subprocess.run(["import","-window",str(a.winfo_id()),capture],check=True)
        a.bin_save()
        rule=[r for r in a.outputs.config.rules if r.kind=="servo"][0]
        self.assertEqual((rule.label,rule.pin,rule.button_pin,rule.active_angle,rule.rest_angle),(1,18,23,80,120))
        self.assertTrue((Path(self.tmp.name)/"outputs.json").exists())
        self.assertEqual(a.step,4)
        self.assertIsNone(a.bin)
        self.assertIn("Bin saved",a.status.get())
        # The GPIO window keeps the button when saved again.
        a.show_outputs(); a.output_dialog.apply()
        self.assertEqual([r for r in a.outputs.config.rules if r.kind=="servo"][0].button_pin,23)

    def test_bin_setup_reports_a_button_that_never_presses(self):
        a=self.app
        a.show_step(5)                              # works before the camera is set up
        self.assertEqual(a.step,5)
        a.bin_vars["closes"].set("down")            # wrong way for the pretend lid
        a.bin_find()
        self.assertTrue(self.wait(lambda:a.bin.lid.state=="closed"))
        a.draw_bin()
        self.assertIsNone(a.bin.closed_angle)
        self.assertIn("didn't press",a.bin_note.cget("text"))
        self.assertEqual(str(a.bin_buttons["save"].cget("state")),"disabled")
        a.bin_vars["button"].set("18")              # same pin as the servo
        a.release_bin(); a.bin_find()
        self.assertIn("different BCM pin",a.status.get())

if __name__=="__main__": unittest.main()
