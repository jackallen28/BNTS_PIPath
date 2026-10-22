"""Drive the real Beginner wiring overlay and runner under Tk (a display is required)."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

try:
    import tkinter as tk
    import gpiozero
    HAVE_UI=bool(os.environ.get('DISPLAY'))
except ImportError:
    HAVE_UI=False


@unittest.skipUnless(HAVE_UI,'requires Tk, gpiozero and a display')
class TestBeginnerWiringUI(unittest.TestCase):
    def setUp(self):
        from pipath import storage
        from pipath.app import PiPathApp
        self.tmp=tempfile.TemporaryDirectory(prefix='pipath-ui-test-')
        root=Path(self.tmp.name)
        self.paths=patch.multiple(storage,APP_HOME=root,STUDENTS=root/'students')
        self.paths.start()
        self.app=PiPathApp()
        self.app.student=storage.create_student('Test student','Test School')
        self.app.student.profile['tour_done']=True
        self.app.login(self.app.student)
        self.app.update()

    def tearDown(self):
        # Drain/cancel shared rich-text layout work before creating another Tk interpreter.
        from pipath.ui.widgets import RichText
        self.app.update_idletasks()
        if RichText._job is not None:
            self.app.after_cancel(RichText._job)
        RichText._job = None
        RichText._waiting.clear()
        self.app.quit_app()
        self.paths.stop()
        self.tmp.cleanup()

    def wait_for(self,predicate,timeout=20):
        deadline=time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:
            self.app.update()
            time.sleep(.01)
        self.assertTrue(predicate(),'Timed out waiting for the student flow')
        self.app.update()

    def to_test(self,guide):
        while guide.i < len(guide.pages)-1:
            guide.forward()
            self.app.update()

    def test_stop_retry_confirm_and_unlock_sorter(self):
        self.app.open_lesson('c3_waste_sorter')
        ws=self.app.screen
        self.app.update()
        guide=ws.wiring_walkthrough
        self.assertIsNotNone(guide)
        self.assertEqual(self.app.grab_current(),guide)
        ws.enter_step(0)
        ws.run()
        self.assertFalse(ws.runner.running)
        self.assertEqual(ws.lp['steps_started'],[])
        self.to_test(guide)
        guide.test()
        self.app.after(150,ws.stop)
        self.wait_for(lambda:not guide.session.running)
        self.assertFalse(guide.session.ready)
        guide.forward()
        self.assertIs(ws.wiring_walkthrough,guide)
        guide.test()
        self.wait_for(lambda:not guide.session.running)
        self.assertTrue(guide.session.passed)
        self.assertIsNotNone(guide.board._photo, "Students must see the camera test picture")
        for item in guide.items[:-1]: guide.confirm(item['id'],True)
        guide.forward()
        self.assertIs(ws.wiring_walkthrough,guide)
        guide.confirm(guide.items[-1]['id'],True)
        self.assertTrue(guide.session.ready)
        self.assertNotIn('PIPATH_CHECK',guide.output.get('1.0','end'))
        guide.forward()
        self.app.update()
        self.assertIsNone(ws.wiring_walkthrough)
        self.assertEqual(ws.view,'step')
        self.assertIn('LED(___)',ws.editor.get_code())
        self.assertNotIn('PIPATH_CHECK',ws.editor.get_code())
        # A camera change needs a new test, even with an already-started lesson.
        ws.camera='usb'
        ws.settings_changed('hardware')
        self.app.update()
        self.assertIsNotNone(ws.wiring_walkthrough)
        self.assertFalse(ws.wiring_walkthrough.session.ready)

    def test_button_interaction_and_context_changes(self):
        self.app.open_lesson('e1_lightswitch')
        ws=self.app.screen
        guide=ws.wiring_walkthrough
        self.to_test(guide)
        guide.test()
        # Press the board button after the LED test has finished.
        self.app.after(3000,lambda:guide.board._press({'kind':'button','pins':[23]}))
        self.app.after(3300,guide.board._release_all)
        self.wait_for(lambda:not guide.session.running)
        self.assertTrue(guide.session.passed)
        for item in guide.items: guide.confirm(item['id'],True)
        guide.forward()
        self.assertIsNone(ws.wiring_walkthrough)
        # Do not touch physical hardware: only verify a mode change relocks the UI.
        ws.real_pi=True
        ws.set_mode('real')
        self.app.update()
        self.assertIsNotNone(ws.wiring_walkthrough)
        self.assertFalse(ws.wiring_walkthrough.session.ready)

    def test_other_help_levels_and_screen_only_lessons_remain_available(self):
        self.app.open_lesson('s1_hello')
        self.assertIsNone(self.app.screen.wiring_walkthrough)
        self.app.student.set_help_level('moderate')
        self.app.open_lesson('c3_waste_sorter')
        self.assertIsNone(self.app.screen.wiring_walkthrough)
        self.app.screen.start_lesson()
        self.assertEqual(self.app.screen.view,'step')
        self.app.student.set_help_level('beginner')
        self.app.screen.settings_changed('help')
        self.assertIsNotNone(self.app.screen.wiring_walkthrough)

    def test_part_images_load_and_are_cached(self):
        from pipath.ui.parts import part_image
        for kind in ('led','rgbled','button','switch','buzzer','pir','distance','servo','resistor','pi','breadboard','camera'):
            with self.subTest(kind=kind):
                image=part_image(self.app,kind,size=96)
                self.assertIsNotNone(image)
                self.assertGreater(image.width(),0)
                self.assertIs(image,part_image(self.app,kind,size=96))

    def test_switching_to_beginner_in_settings_gates_on_done(self):
        self.app.student.set_help_level('moderate')
        self.app.open_lesson('c3_waste_sorter')
        ws=self.app.screen
        ws.start_lesson()
        self.app.open_settings('help')
        self.app.student.set_help_level('beginner')
        self.app.settings_changed('help')
        self.assertIsNone(ws.wiring_walkthrough)
        self.app._settings.close()
        self.app.update()
        self.assertIsNotNone(ws.wiring_walkthrough)
        self.assertEqual(self.app.grab_current(),ws.wiring_walkthrough)

    def test_launch_updater_falls_back_offline_and_restarts_only_once(self):
        from pipath.updater import UpdateResult, launch_update_check
        with patch.dict(os.environ,{'PIPATH_AUTO_UPDATE':'1'}):
            os.environ.pop('PIPATH_UPDATE_RESTARTED',None)
            with patch('pipath.gpio.on_real_pi',return_value=True), patch('pipath.updater.check_and_update',return_value=UpdateResult('offline','Opening installed version')):
                self.assertTrue(launch_update_check(Path(self.tmp.name)))
            with patch('pipath.gpio.on_real_pi',return_value=True), patch('pipath.updater.check_and_update',return_value=UpdateResult('updated','Opening new version')), patch('os.execv') as restart:
                self.assertTrue(launch_update_check(Path(self.tmp.name)))
                restart.assert_called_once()
                self.assertEqual(os.environ['PIPATH_UPDATE_RESTARTED'],'1')
                self.assertTrue(launch_update_check(Path(self.tmp.name)))
                restart.assert_called_once()
                self.assertNotIn('PIPATH_UPDATE_RESTARTED',os.environ)
