"""Colour/shape extraction adapted from the user-supplied ML Camera app.
Only the marked inspection area is analysed. No identity recognition is used.
"""
import math
from dataclasses import dataclass
import cv2
import numpy as np
PROC_W, PROC_H = 320, 240
MIN_OBJECT_AREA = .01
HUE_BINS = 18
N_COLOUR = 24
N_SHAPE = 5
KERNEL_SMALL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
KERNEL_BIG = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))


def shrink(frame):
    return cv2.resize(frame, (PROC_W, PROC_H), interpolation=cv2.INTER_AREA)


def to_lab(small):
    blurred = cv2.GaussianBlur(small, (5, 5), 0)
    return cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB).astype(np.float32)


def difference_mask(small, background_lab, threshold):
    """White wherever the picture is different from the empty table."""
    diff = to_lab(small) - background_lab
    # Webcams adjust their brightness and colour by themselves when something
    # appears. Most of the picture is still table, so the middle (median)
    # change is the camera adjusting - take it away.
    shift = np.median(diff[::4, ::4].reshape(-1, 3), axis=0)
    diff -= np.clip(shift, [-40, -10, -10], [40, 10, 10])
    # Brightness changes count less than colour changes, so shadows matter less.
    dist = np.sqrt(0.5 * diff[..., 0] ** 2 + diff[..., 1] ** 2 + diff[..., 2] ** 2)
    mask = (dist > threshold).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, KERNEL_SMALL)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, KERNEL_BIG, iterations=2)
    return mask


def biggest_object(mask):
    contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
    if not contours:
        return None
    best = max(contours, key=cv2.contourArea)
    if cv2.contourArea(best) < MIN_OBJECT_AREA * PROC_W * PROC_H:
        return None
    return best


# ---------------------------------------------------------------------------
# Measuring the object: turn it into numbers ("features")
# ---------------------------------------------------------------------------

HUE_BINS = 18
N_COLOUR = HUE_BINS + 4 + 2
N_SHAPE = 5


def measure(small, contour):
    """Describe an object with numbers: colour first, then shape."""
    x, y, w, h = cv2.boundingRect(contour)
    crop = small[y:y + h, x:x + w]
    mask = np.zeros((h, w), np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, -1, offset=(-x, -y))
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    pixels = hsv[mask > 0].astype(np.float32)
    if len(pixels) == 0:
        pixels = hsv.reshape(-1, 3).astype(np.float32)
    hue, sat, val = pixels[:, 0], pixels[:, 1], pixels[:, 2]

    # Colour: which colours are in it (a hue histogram), softened a little so
    # a colour sitting on the edge of two bins doesn't jump between them.
    colourful = (sat > 60) & (val > 50)
    hist = np.bincount((hue[colourful] // 10).astype(int), weights=sat[colourful],
                       minlength=HUE_BINS)[:HUE_BINS]
    hist = 0.5 * hist + 0.25 * np.roll(hist, 1) + 0.25 * np.roll(hist, -1)
    if hist.sum() > 0:
        hist = hist / hist.sum() * colourful.mean()
    # ...plus how much of it is black/grey/white (each pixel is shared between
    # the two nearest levels), and how bright it is.
    level = val[~colourful] / 255.0 * 3
    low = np.minimum(level.astype(int), 2)
    part = level - low
    grey = (np.bincount(low, 1 - part, 4) + np.bincount(low + 1, part, 4))[:4] / float(len(pixels))
    colour = np.concatenate([hist, grey, [sat.mean() / 255.0, val.mean() / 255.0]])

    # Shape
    area = max(cv2.contourArea(contour), 1.0)
    _, (rw, rh), _ = cv2.minAreaRect(contour)
    long_side, short_side = max(rw, rh, 1.0), max(min(rw, rh), 1.0)
    hull_area = max(cv2.contourArea(cv2.convexHull(contour)), 1.0)
    perimeter = max(cv2.arcLength(contour, True), 1.0)
    shape = [
        math.log(long_side / short_side),          # long and thin?
        area / (long_side * short_side),           # how rectangular?
        area / hull_area,                          # solid, or has a handle?
        4 * math.pi * area / perimeter ** 2,       # how round?
        math.sqrt(area / float(PROC_W * PROC_H)),  # how big?
    ]
    return np.concatenate([colour, shape]).astype(np.float32)



@dataclass
class Observation:
    feature: np.ndarray | None
    contour: np.ndarray | None
    reason: str
    moving: bool


def inspect(frame, background, previous=None, threshold=22):
    small = shrink(frame)
    moving = previous is None or float(np.mean(cv2.absdiff(small, previous))) > 2.5
    mask = difference_mask(small, background, threshold)
    contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
    contours = [c for c in contours if cv2.contourArea(c) >= .01 * PROC_W * PROC_H]
    if not contours:
        return Observation(None, None, "Show one item in the inspection area", moving), small
    contour = max(contours, key=cv2.contourArea)
    feature = measure(small, contour)
    x, y, w, h = cv2.boundingRect(contour)
    area = cv2.contourArea(contour) / (PROC_W * PROC_H)
    reason = ""
    if len(contours) > 1:
        reason = "Show one item at a time; move hands away"
    elif area > .60:
        reason = "Too much of the area is covered; move hands or people away"
    elif x <= 3 or y <= 3 or x+w >= PROC_W-3 or y+h >= PROC_H-3:
        reason = "Keep the whole item inside the inspection area"
    return Observation(feature, contour, reason, moving), small


def inspection_crop(frame):
    # Centre 60% of a 4:3 camera image: the border is context, never training data.
    h, w = frame.shape[:2]
    return frame[int(h*.2):int(h*.8), int(w*.2):int(w*.8)]
