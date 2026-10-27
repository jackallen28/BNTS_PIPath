"""The supplied ML Camera's colour/shape scaling, weighted kNN and novelty check."""
from dataclasses import dataclass
import math
import time
import numpy as np
from .vision import N_COLOUR, N_SHAPE

LABELS=("Waste", "Recycling")
MIN_PHOTOS=10
K_NEIGHBOURS=5

@dataclass
class Sample:
    feature: np.ndarray
    label: int
    group: str = ""

@dataclass
class Prediction:
    label: int | None
    similarity: float
    reason: str


def requirements(samples):
    missing=[]
    for label,name in enumerate(LABELS):
        count=sum(s.label==label for s in samples)
        if count<MIN_PHOTOS: missing.append(f"{name}: {count}/{MIN_PHOTOS} photos")
    return missing


class Model:
    def __init__(self, samples):
        features=[s.feature for s in samples]
        labels=[s.label for s in samples]
        if len(samples)<2:
            raise ValueError("Take more example photos first")
        if any(type(label) is not int or label not in (0,1) for label in labels):
            raise ValueError("Train only Waste and Recycling examples")
        self.probs=None
        self.X = np.asarray(features, np.float32)
        self.y = np.asarray(labels, int)
        if self.X.shape != (len(labels),29) or not np.isfinite(self.X).all():
            raise ValueError("Invalid training measurements")
        self.k = max(1, min(K_NEIGHBOURS, len(self.y) - 1))
        # Learn how much the numbers normally vary, so colour and shape count
        # equally and no single number is allowed to shout over the others.
        self.mean = self.X.mean(axis=0)
        self.scale = np.ones(self.X.shape[1], np.float32)
        colour_spread = math.sqrt(float(self.X[:, :N_COLOUR].var(axis=0).sum()))
        self.scale[:N_COLOUR] = max(colour_spread, 0.05)
        shape_std = np.maximum(self.X[:, N_COLOUR:].std(axis=0), 0.05)
        self.scale[N_COLOUR:] = shape_std * math.sqrt(N_SHAPE)
        self.Z = (self.X - self.mean) / self.scale

        # Quiz: hide each photo in turn and guess it from all the others.
        self.quiz = []
        nearest = []
        for i in range(len(self.y)):
            probs, _, dist = self._vote(self._distances(self.Z[i]), skip=i)
            self.quiz.append(int(np.argmax(probs)))
            nearest.append(dist)
        # Anything much further away than usual is something new.
        self.unknown_dist = max(3.0 * float(np.percentile(nearest, 90)), 1.5)

    def _distances(self, z):
        return np.sqrt(((self.Z - z) ** 2).sum(axis=1))

    def _vote(self, dists, skip=None):
        order = np.argsort(dists, kind="stable")  # equal distances: same order on every NumPy
        if skip is not None:
            order = order[order != skip]
        votes = np.zeros(len(LABELS))
        for i in order[:self.k]:
            votes[self.y[i]] += 1.0 / (dists[i] + 0.1)  # closer photos get a bigger vote
        return votes / votes.sum(), int(order[0]), float(dists[order[0]])

    def vote(self, feature):
        """Returns similarity votes, nearest photo index and feature distance."""
        z = (feature - self.mean) / self.scale
        return self._vote(self._distances(z))


    def reset_prediction(self):
        self.probs=None

    def predict(self, feature):
        if feature is None:
            self.reset_prediction()
            return Prediction(None,0,"Show an item on the table")
        probs, nearest, distance=self.vote(feature)
        self.probs=probs if self.probs is None else .5*self.probs+.5*probs
        best=int(np.argmax(self.probs))
        support=float(self.probs[best])
        if distance>self.unknown_dist:
            return Prediction(None,support,"I don't know this item: bin stays closed")
        if support<.55:
            return Prediction(None,support,"Not sure yet: bin stays closed")
        return Prediction(best,support,"")

    @staticmethod
    def training_quiz(samples):
        # Same leave-one-photo-out teaching quiz as the original camera app.
        model=Model(samples)
        rows=[]
        for label,name in enumerate(LABELS):
            indices=[i for i,s in enumerate(samples) if s.label==label]
            right=sum(model.quiz[i]==label for i in indices)
            rows.append({"label":label,"group":name,"total":len(indices),
                         "correct":right,"withheld":0,"wrong_bin":len(indices)-right})
        return rows

class SteadyGate:
    def __init__(self, seconds=.5):
        self.seconds = seconds
        self.reset()

    def reset(self):
        self.label = None
        self.since = None

    def apply(self, prediction, reason="", moving=False, now=None):
        now = time.monotonic() if now is None else now
        if reason or prediction.label is None:
            self.reset()
            return Prediction(None, prediction.similarity, reason or prediction.reason)
        if self.label != prediction.label:
            self.label, self.since = prediction.label, now
        if now-self.since < self.seconds:
            return Prediction(None, prediction.similarity, "Hold still: checking the item…")
        return prediction
