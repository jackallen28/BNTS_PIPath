"""Versioned, atomic local measurements; camera photographs are not saved."""
import os
from pathlib import Path
import tempfile
import zipfile
import numpy as np
from .model import Sample


def save(path, samples, background):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".npz")
    try:
        with os.fdopen(fd, "wb") as f:
            np.savez_compressed(f, version=np.array([2]),
                features=np.array([s.feature for s in samples], dtype=np.float32).reshape(-1,29),
                labels=np.array([s.label for s in samples], dtype=np.int32),
                groups=np.array([s.group for s in samples], dtype="U80"), background=background)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def load(path):
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > 10_000_000:
            raise ValueError("Training file is too large")
    with np.load(path, allow_pickle=False) as d:
        if d["version"].tolist() != [2]:
            raise ValueError("Older cropped-camera training needs new photos for the full-frame model")
        x, y, groups, bg = (d[k] for k in ("features","labels","groups","background"))
        if x.shape != (len(y),29) or not 0 <= len(y) <= 480:
            raise ValueError("Unsupported training file")
        if groups.shape != y.shape or bg.shape != (240,320,3):
            raise ValueError("Invalid training file shapes")
        if not np.isfinite(x).all() or not np.isfinite(bg).all() or not np.isin(y,[0,1]).all():
            raise ValueError("Invalid training measurements")
        if any(not str(g).strip() or len(str(g)) > 80 for g in groups):
            raise ValueError("Invalid item names")
        return [Sample(f.copy(),int(c),str(g)) for f,c,g in zip(x,y,groups)], bg.astype(np.float32)
