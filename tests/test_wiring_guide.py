"""The wiring gate needs completed tests AND student observation; exercise real mock GPIO."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pipath.content import Catalog
from pipath.wiring_guide import WiringSession, guide_pages, wiring_test_program, test_items
from shimrun import HAVE_GPIOZERO, run_shim


class TestWiringGate(unittest.TestCase):
    def test_no_bypass_on_partial_failed_stopped_or_crashed_test(self):
        session = WiringSession({'0','camera'})
        success = 'PIPATH_CHECK:0:PASS\nPIPATH_CHECK:camera:PASS\nPIPATH_CHECK:DONE\n'
        for stdout,stderr,rc,reason in [(success,'',0,'user'), (success,'',1,None),
                (success.replace('camera:PASS','camera:FAIL'),'',0,None),
                (success.replace('PIPATH_CHECK:DONE',''),'',0,None),
                (success,'Traceback: camera failed',0,None)]:
            session.start()
            session.finish(stdout,stderr,rc,reason)
            for ident in session.expected: session.confirm(ident,True)
            self.assertFalse(session.ready)
        session.start()
        session.finish(success,'',0,None)
        self.assertFalse(session.ready)
        session.confirm('0',True)
        self.assertFalse(session.ready)
        session.confirm('camera',True)
        self.assertTrue(session.ready)
        session.confirm('0',False)
        self.assertFalse(session.ready)
        session.start()
        self.assertFalse(session.ready)

    def test_every_hardware_lesson_has_explanations_and_supported_test(self):
        cat=Catalog()
        kinds={'led','button','switch','buzzer','rgbled','pir','distance','servo','camera'}
        for project in cat.projects:
            lesson=cat.lesson(project['id'])
            if not (lesson.get('requires_gpio') or lesson.get('requires_camera')): continue
            with self.subTest(project=project['id']):
                self.assertEqual(guide_pages(lesson)[0]['kind'],'safety')
                self.assertEqual(guide_pages(lesson)[-1]['kind'],'test')
                self.assertTrue(all(i['kind'] in kinds for i in test_items(lesson)))
                compile(wiring_test_program(lesson),'<hidden wiring test>','exec')

    @unittest.skipUnless(HAVE_GPIOZERO,'requires gpiozero')
    def test_hidden_sorter_test_exercises_leds_servo_and_camera(self):
        lesson=Catalog().lesson('c3_waste_sorter')
        r=run_shim(wiring_test_program(lesson))
        session=WiringSession({i['id'] for i in test_items(lesson)})
        session.finish(r.stdout,r.stderr,r.rc,None)
        self.assertTrue(session.passed,r.stderr+r.stdout)
        self.assertTrue(r.ever_on(17))
        self.assertTrue(r.ever_on(22))
        positions=[m['pins'].get('18') for m in r.messages if m.get('t')=='pins']
        self.assertIn(-0.5,positions)
        self.assertIn(0.5,positions)
        self.assertTrue(any(m.get('t')=='photo' for m in r.messages))

    @unittest.skipUnless(HAVE_GPIOZERO,'requires gpiozero')
    def test_inputs_really_need_press_and_release(self):
        lesson={'wiring':[{'part':'Button','kind':'button','pin':23}]}
        code=wiring_test_program(lesson)
        r=run_shim(code,events=['0.5 tap 23'])
        session=WiringSession({'0'})
        session.finish(r.stdout,r.stderr,r.rc,None)
        self.assertTrue(session.passed,r.stderr+r.stdout)
        # A held button cannot satisfy the release phase; stopping cannot pass.
        r=run_shim(code,events=['0.5 press 23'],seconds=1)
        session.finish(r.stdout,r.stderr,r.rc,'user')
        self.assertFalse(session.passed)

    @unittest.skipUnless(HAVE_GPIOZERO,'requires gpiozero')
    def test_sensor_tests_require_a_response(self):
        for row,events in [({'part':'Distance','kind':'distance','pins':[26,4]},['0.5 distance 26 10']),
                           ({'part':'Motion','kind':'pir','pin':23},['0.5 press 23'])]:
            with self.subTest(kind=row['kind']):
                r=run_shim(wiring_test_program({'wiring':[row]}),events=events)
                session=WiringSession({'0'})
                session.finish(r.stdout,r.stderr,r.rc,None)
                self.assertTrue(session.passed,r.stdout+r.stderr)
