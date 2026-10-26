import tempfile
from pathlib import Path
import unittest
import numpy as np
from wastepath.model import Sample, Model, Prediction, SteadyGate, requirements
from wastepath.storage import save, load
from wastepath.camera import demo_frame
from wastepath.vision import inspect, inspection_crop, to_lab, shrink


def samples():
    rng=np.random.default_rng(12)
    return [Sample(np.full(29,label*3,dtype=np.float32)+rng.normal(0,.025,29),label,f"item {label}-{group}")
            for label in range(3) for group in range(2) for _ in range(8)]

class ModelTests(unittest.TestCase):
    def test_known_bins_and_negative_examples(self):
        model=Model(samples())
        self.assertEqual(model.predict(np.zeros(29)).label,0)
        self.assertEqual(model.predict(np.full(29,3)).label,1)
        p=model.predict(np.full(29,6))
        self.assertIsNone(p.label)
        self.assertIn("person",p.reason)

    def test_unknown_is_withheld_even_with_unanimous_votes(self):
        p=Model(samples()).predict(np.full(29,-30))
        self.assertIsNone(p.label)
        self.assertIn("new",p.reason)

    def test_ambiguous_votes_withheld(self):
        rng=np.random.default_rng(2)
        data=[Sample(rng.normal(0,.01,29),i%2,str(i)) for i in range(40)]
        data.extend(Sample(np.full(29,8),2,str(i)) for i in range(8))
        found=[Model(data).predict(rng.normal(0,.01,29)) for _ in range(20)]
        self.assertTrue(any(p.label is None and "disagree" in p.reason for p in found))

    def test_groups_required_and_quiz_leaves_whole_items_out(self):
        bank=samples()
        self.assertEqual(requirements(bank),[])
        self.assertTrue(requirements([s for s in bank if s.group!="item 0-1"]))
        rows=Model.group_quiz(bank)
        self.assertEqual(len(rows),6)
        self.assertTrue(all(r['total']==8 for r in rows))
        self.assertTrue(all(r['correct']==8 for r in rows if r['label']<2))
        self.assertTrue(all(r['withheld']==8 for r in rows if r['label']==2))

    def test_steady_gate_resets_on_motion_absence_change_and_quality(self):
        gate=SteadyGate(1)
        waste=Prediction(0,1,"")
        self.assertIsNone(gate.apply(waste,now=0).label)
        self.assertEqual(gate.apply(waste,now=1.1).label,0)
        self.assertIsNone(gate.apply(waste,moving=True,now=1.2).label)
        self.assertIsNone(gate.apply(waste,now=1.3).label)
        self.assertIsNone(gate.apply(waste,reason="hand in view",now=2.4).label)
        self.assertIsNone(gate.apply(waste,now=2.5).label)
        self.assertIsNone(gate.apply(Prediction(None,0,"empty"),now=4).label)
        self.assertIsNone(gate.apply(waste,now=4.1).label)
        self.assertIsNone(gate.apply(Prediction(1,1,""),now=5.2).label)

class VisionTests(unittest.TestCase):
    def setUp(self):
        self.bg=to_lab(shrink(inspection_crop(demo_frame())))
    def observe(self,kind):
        crop=inspection_crop(demo_frame(kind))
        return inspect(crop,self.bg,shrink(crop))[0]
    def test_empty_and_people_outside_inspection_area_are_excluded(self):
        self.assertIsNone(self.observe("Empty table").feature)
        self.assertIsNone(self.observe("Person outside area").feature)
    def test_clean_item_has_features_and_hand_crossing_edge_is_blocked(self):
        o=self.observe("Recycling")
        self.assertEqual(o.feature.shape,(29,))
        self.assertFalse(o.reason)
        hand=self.observe("People / hands / other")
        self.assertIsNotNone(hand.feature)
        self.assertIn("inside",hand.reason)
    def test_movement_detected(self):
        crop=inspection_crop(demo_frame("Waste"))
        empty=shrink(inspection_crop(demo_frame()))
        o,_=inspect(crop,self.bg,empty)
        self.assertTrue(o.moving)
    def test_demo_pipeline_bins_and_negative(self):
        bank=[]
        for label,kind in enumerate(("Waste","Recycling","People / hands / other")):
            for group in range(2):
                for view in range(8):
                    crop=inspection_crop(demo_frame(kind,view+group))
                    o,_=inspect(crop,self.bg,shrink(crop))
                    bank.append(Sample(o.feature,label,f"{kind}-{group}"))
        model=Model(bank)
        self.assertEqual(model.predict(self.observe("Waste").feature).label,0)
        self.assertEqual(model.predict(self.observe("Recycling").feature).label,1)
        self.assertIsNone(model.predict(self.observe("People / hands / other").feature).label)

class StorageTests(unittest.TestCase):
    def test_roundtrip_and_atomic_replace(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"data.npz"
            bg=np.zeros((240,320,3),np.float32)
            save(p,samples(),bg)
            bank,background=load(p)
            self.assertEqual(len(bank),48)
            np.testing.assert_array_equal(bank[0].feature,samples()[0].feature.astype(np.float32))
            save(p,[],bg)
            self.assertEqual(load(p)[0],[])
            self.assertEqual(list(Path(folder).iterdir()),[p])
    def test_invalid_version_and_nonfinite_measurements_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"bad.npz"
            for version,x in ((2,np.zeros((1,29))),(1,np.full((1,29),np.nan))):
                np.savez(p,version=[version],features=x,labels=[0],groups=['x'],background=np.zeros((240,320,3)))
                with self.assertRaises(ValueError): load(p)

if __name__=="__main__": unittest.main()
