"""Exercise both sorting routes with held-out simulator captures."""
import json
import shutil
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from shimrun import HAVE_GPIOZERO, run_shim
from pipath.content import Catalog, DATA_DIR


@unittest.skipUnless(HAVE_GPIOZERO, "gpiozero is not installed")
class TestWasteSorter(unittest.TestCase):
    def test_both_routes_and_servo_reporting(self):
        code = Catalog().lesson('c3_waste_sorter')['steps'][-1]['demo']
        # Keep held-out simulator views reproducible; real camera accuracy is evaluated by students.
        code = code.replace('cam = Camera()', 'cam = Camera()\ncam._rng.seed(0)')
        for obj, label, pin, position in [('ball', 'waste', 17, -0.5),
                                          ('box', 'recycling', 22, 0.5)]:
            with self.subTest(label=label):
                r = run_shim(code, stdin='\nq\n', env={'PIPATH_CAMERA_OBJECT': obj},
                             files=[DATA_DIR / 'demo_files/c3/waste_examples.json'])
                self.assertEqual(r.rc, 0, r.stderr)
                self.assertIn('Prediction: ' + label, r.stdout)
                self.assertTrue(r.ever_on(pin))
                self.assertIn({'kind': 'Servo', 'pins': [18]}, r.devices)
                positions = [m['pins']['18'] for m in r.messages
                             if m.get('t') == 'pins' and '18' in m['pins']]
                self.assertIn(position, positions)
                self.assertIn(0, positions)

    def test_training_saves_two_distinct_labelled_groups(self):
        step = Catalog().lesson('c3_waste_sorter')['steps'][4]
        r = run_shim(step['demo'], stdin=step['demo_input'],
                     events=step['demo_events'], keep_folder=True)
        try:
            self.assertEqual(r.rc, 0, r.stderr)
            examples = json.loads((r.folder / 'waste_examples.json').read_text())
            self.assertEqual([e['label'] for e in examples], ['waste'] * 5 + ['recycling'] * 5)
            self.assertTrue(all(len(e['pixels']) == 256 for e in examples))
            self.assertTrue(all(0 <= n <= 255 for e in examples for n in e['pixels']))
            self.assertNotEqual(examples[0]['pixels'], examples[-1]['pixels'])
        finally:
            shutil.rmtree(r.folder)
