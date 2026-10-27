import hashlib
import json
import tempfile
from pathlib import Path
import unittest
import cv2
import numpy as np
from wastepath.model import LABELS, Sample, Model, Prediction, SteadyGate, requirements
from wastepath.storage import save, load
from wastepath.camera import demo_frame, normalise_frame
from wastepath.vision import inspect, to_lab, shrink, difference_mask


def samples():
    rng=np.random.default_rng(12)
    return [Sample(np.full(29,label*3,dtype=np.float32)+rng.normal(0,.025,29),label,f"item {label}")
            for label in range(2) for _ in range(10)]

class ModelTests(unittest.TestCase):
    def test_ten_photos_per_category_suffice_without_people_or_named_groups(self):
        self.assertEqual(LABELS,("Waste","Recycling"))
        self.assertEqual(requirements(samples()),[])
        self.assertTrue(requirements(samples()[:-1]))
        model=Model(samples())
        self.assertEqual(model.predict(np.zeros(29)).label,0)
        model.reset_prediction()
        self.assertEqual(model.predict(np.full(29,3)).label,1)
        with self.assertRaises(ValueError): Model(samples()+[Sample(np.zeros(29),2)])

    def test_unknown_is_rejected_even_with_unanimous_votes(self):
        p=Model(samples()).predict(np.full(29,-30))
        self.assertIsNone(p.label)
        self.assertIn("don't know",p.reason)

    def test_equal_votes_are_unsure_and_smoothing_resets_for_empty_table(self):
        # Coincident measurements with opposing labels cannot decide a bin.
        bank=[Sample(np.zeros(29),i%2) for i in range(20)]
        model=Model(bank)
        model.k=4
        self.assertIsNone(model.predict(np.zeros(29)).label)
        model.predict(None)
        self.assertIsNone(model.probs)

    def test_photo_quiz_excludes_the_photo_and_reports_both_categories(self):
        rows=Model.training_quiz(samples())
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r['total']==10 and r['correct']==10 for r in rows))

    def test_action_gate_needs_consistency_and_clears_on_absence_or_change(self):
        gate=SteadyGate(.5)
        waste=Prediction(0,1,"")
        self.assertIsNone(gate.apply(waste,now=0).label)
        self.assertEqual(gate.apply(waste,now=.6).label,0)
        self.assertIsNone(gate.apply(Prediction(None,0,"empty"),now=.7).label)
        self.assertIsNone(gate.apply(waste,now=.8).label)
        self.assertEqual(gate.apply(waste,now=1.4).label,0)
        self.assertIsNone(gate.apply(Prediction(1,1,""),now=1.5).label)

    def test_votes_scaling_novelty_and_photo_quiz_match_uploaded_original(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/ml_camera_reference.json').read_text())
        bank=[Sample(np.array(f,np.float32),label) for f,label in zip(fixture['features'],fixture['labels'])]
        model=Model(bank)
        np.testing.assert_allclose(model.scale,fixture['scale'],rtol=1e-6)
        self.assertAlmostEqual(model.unknown_dist,fixture['unknown_dist'],places=6)
        self.assertEqual(model.quiz,fixture['quiz'])
        for case in fixture['queries']:
            votes,index,distance=model.vote(np.array(case['feature'],np.float32))
            np.testing.assert_allclose(votes,case['votes'],atol=1e-6)
            self.assertEqual(index,case['nearest'])
            self.assertAlmostEqual(distance,case['distance'],places=6)

class VisionTests(unittest.TestCase):
    def setUp(self): self.bg=to_lab(shrink(demo_frame()))
    def test_empty_table_and_full_frame_object_detection(self):
        self.assertIsNone(inspect(demo_frame(),self.bg)[0].feature)
        frame=demo_frame()
        cv2.rectangle(frame,(10,160),(105,280),(170,80,35),-1)
        o,_=inspect(frame,self.bg)
        self.assertIsNotNone(o.feature)  # The previous central crop missed this object.
        self.assertFalse(o.reason)
    def test_largest_changed_object_is_used_without_extra_edge_or_motion_gates(self):
        frame=demo_frame("Waste")
        cv2.rectangle(frame,(0,0),(35,35),(30,150,220),-1)
        o,_=inspect(frame,self.bg,shrink(demo_frame()))
        self.assertEqual(o.feature.shape,(29,))
        self.assertFalse(o.reason)
        self.assertGreater(cv2.boundingRect(o.contour)[0],35)
    def test_demo_pipeline_matches_bins_and_rejects_unfamiliar_item(self):
        bank=[]
        for label,kind in enumerate(LABELS):
            for view in range(10):
                frame=demo_frame(kind,view)
                bank.append(Sample(inspect(frame,self.bg)[0].feature,label))
        model=Model(bank)
        for label,kind in enumerate(LABELS):
            model.reset_prediction()
            self.assertEqual(model.predict(inspect(demo_frame(kind),self.bg)[0].feature).label,label)
        self.assertIsNone(model.predict(inspect(demo_frame('Unknown item'),self.bg)[0].feature).label)
    def test_original_segmentation_and_measurements_reference(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/ml_camera_reference.json').read_text())
        for case in fixture['images']:
            frame=demo_frame(case['kind'],case['variation'])
            small=shrink(frame)
            mask=difference_mask(small,self.bg,22)
            self.assertEqual(hashlib.sha256(mask.tobytes()).hexdigest(),case['mask_sha256'])
            # Pi OS ships an older OpenCV whose resize rounds a few edge pixels differently.
            np.testing.assert_allclose(inspect(frame,self.bg)[0].feature,case['feature'],atol=1e-3)
    def test_widescreen_camera_is_cropped_without_stretching_shapes(self):
        frame=np.zeros((480,960,3),np.uint8)
        frame[:,160:800]=demo_frame('Recycling')
        np.testing.assert_array_equal(normalise_frame(frame),demo_frame('Recycling'))

class StorageTests(unittest.TestCase):
    def test_roundtrip_and_atomic_replace(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"data.npz"; bg=np.zeros((240,320,3),np.float32)
            save(p,samples(),bg)
            bank,background=load(p)
            self.assertEqual(len(bank),20)
            np.testing.assert_array_equal(bank[0].feature,samples()[0].feature.astype(np.float32))
            save(p,[],bg)
            self.assertEqual(load(p)[0],[])
            self.assertEqual(list(Path(folder).iterdir()),[p])
    def test_previous_cropped_training_and_invalid_measurements_rejected_without_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"bad.npz"
            for version,x,label in ((1,np.zeros((1,29)),0),(2,np.full((1,29),np.nan),0),(2,np.zeros((1,29)),2)):
                np.savez(p,version=[version],features=x,labels=[label],groups=['x'],background=np.zeros((240,320,3)))
                original=p.read_bytes()
                with self.assertRaises(ValueError): load(p)
                self.assertEqual(p.read_bytes(),original)

if __name__=="__main__": unittest.main()
