"""Small, inspectable kNN classifier. Votes are similarity, not probability."""
from dataclasses import dataclass
import time
import numpy as np

LABELS = ("Waste", "Recycling", "People / hands / other")
MIN_PHOTOS = 8
MIN_GROUPS = 2

@dataclass
class Sample:
    feature: np.ndarray
    label: int
    group: str

@dataclass
class Prediction:
    label: int | None
    similarity: float
    reason: str


def requirements(samples):
    missing = []
    for label, name in enumerate(LABELS):
        groups = {s.group for s in samples if s.label == label}
        complete = sum(sum(s.label == label and s.group == g for s in samples) >= MIN_PHOTOS for g in groups)
        if complete < MIN_GROUPS:
            missing.append(f"{name}: {complete}/{MIN_GROUPS} sets with {MIN_PHOTOS}+ photos")
    return missing


class Model:
    def __init__(self, samples):
        if len(samples) < 2:
            raise ValueError("More examples are needed")
        self.x = np.asarray([s.feature for s in samples], dtype=np.float32)
        self.y = np.asarray([s.label for s in samples], dtype=np.int32)
        if self.x.ndim != 2 or self.x.shape[1] != 29 or not np.isfinite(self.x).all():
            raise ValueError("Invalid training measurements")
        self.mean = self.x.mean(axis=0)
        self.scale = np.maximum(self.x.std(axis=0), .08)
        self.z = (self.x-self.mean)/self.scale / np.sqrt(29)
        # Each class gets its own novelty limit, using nearest same-class examples.
        self.limits = {}
        for label in range(3):
            points = self.z[self.y == label]
            if len(points) < 2:
                self.limits[label] = 0
                continue
            distances = np.sqrt(((points[:, None]-points[None, :])**2).sum(axis=2))
            np.fill_diagonal(distances, np.inf)
            self.limits[label] = max(.25, min(2., float(np.quantile(distances.min(axis=1), .95))*2.5))

    def predict(self, feature):
        if feature is None:
            return Prediction(None, 0, "No item to classify")
        z = (np.asarray(feature)-self.mean)/self.scale/np.sqrt(29)
        d = np.sqrt(((self.z-z)**2).sum(axis=1))
        order = np.argsort(d)[:min(5, len(d))]
        votes = np.bincount(self.y[order], weights=1/(d[order]+.03), minlength=3)
        votes /= votes.sum()
        best = int(votes.argmax())
        support = float(votes[best])
        if best == 2:
            return Prediction(None, support, "Looks like a person, hand or other example: no bin choice")
        if d[order[0]] > self.limits[best]:
            return Prediction(None, support, "This looks new. Add varied examples or check the local rules")
        ranked = np.sort(votes)
        if support < .8 or ranked[-1]-ranked[-2] < .35:
            return Prediction(None, support, "The examples disagree: I am not sure")
        return Prediction(best, support, "")

    @staticmethod
    def group_quiz(samples):
        # Leave a whole named item/scene out, not just a nearly identical photo.
        rows = []
        for label, group in sorted({(s.label, s.group) for s in samples}):
            train = [s for s in samples if (s.label, s.group) != (label, group)]
            test = [s for s in samples if (s.label, s.group) == (label, group)]
            model = Model(train)
            guesses = [model.predict(s.feature).label for s in test]
            rows.append({"label":label,"group":group,"total":len(test),
                         "correct":sum(g == label for g in guesses) if label != 2 else 0,
                         "withheld":sum(g is None for g in guesses),
                         "wrong_bin":sum(g is not None and g != label for g in guesses)})
        return rows


class SteadyGate:
    def __init__(self, seconds=1.0):
        self.seconds = seconds
        self.reset()

    def reset(self):
        self.label = None
        self.since = None

    def apply(self, prediction, reason="", moving=False, now=None):
        now = time.monotonic() if now is None else now
        if reason or moving or prediction.label is None:
            self.reset()
            return Prediction(None, prediction.similarity, reason or ("Hold still and move hands away" if moving else prediction.reason))
        if self.label != prediction.label:
            self.label, self.since = prediction.label, now
        if now-self.since < self.seconds:
            return Prediction(None, prediction.similarity, "Hold still: checking the item…")
        return prediction
