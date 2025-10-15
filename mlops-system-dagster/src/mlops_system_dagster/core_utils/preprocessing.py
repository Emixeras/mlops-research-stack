"""Preprocessing & feature extraction utilities shared across training, assets, and serving."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, List, Tuple
from sklearn.preprocessing import StandardScaler

import numpy as np
from PIL import Image

# Central configuration defaults
IMAGE_SIZE = (64, 64)
IMAGE_MODE = "L"  # grayscale
FLATTEN = True
ROW_LIMIT = 100  # consumed by training assets

DEFAULT_PREPROCESS_CONFIG = {
    "image_size": IMAGE_SIZE,
    "image_mode": IMAGE_MODE,
    "flatten": FLATTEN,
}


def load_and_flatten(image_path: Path, *, config: dict | None = None) -> np.ndarray | None:
    """Load an image from path and apply standard preprocessing -> flat vector.

    Returns None if file does not exist.
    """
    if not image_path.exists():
        return None
    cfg = config or DEFAULT_PREPROCESS_CONFIG
    with Image.open(image_path).convert(cfg.get("image_mode", IMAGE_MODE)) as img:
        arr = np.array(img.resize(tuple(cfg.get("image_size", IMAGE_SIZE))))
        if cfg.get("flatten", FLATTEN):
            return arr.flatten()
        return arr


def coerce_images(raw: Any, *, config: dict | None = None) -> List[Image.Image]:
    """Normalize supported raw inputs into a list of PIL Images.

    Supported inputs: single path/bytes, list/tuple of paths or bytes.
    """
    cfg = config or DEFAULT_PREPROCESS_CONFIG
    mode = cfg.get("image_mode", IMAGE_MODE)
    if raw is None:
        return []
    if isinstance(raw, (str, Path, bytes)):
        raw = [raw]
    out: List[Image.Image] = []
    for item in raw:  # type: ignore
        if isinstance(item, (str, Path)):
            img = Image.open(item).convert(mode)
        elif isinstance(item, bytes):
            img = Image.open(io.BytesIO(item)).convert(mode)
        else:
            raise TypeError(f"Unsupported input element type: {type(item)}")
        out.append(img)
    return out


def prepare_image(img: Image.Image, *, config: dict | None = None) -> np.ndarray:
    """Resize + flatten (if configured) a PIL image -> feature vector/array."""
    cfg = config or DEFAULT_PREPROCESS_CONFIG
    size = tuple(cfg.get("image_size", IMAGE_SIZE))
    arr = np.array(img.resize(size))
    if cfg.get("flatten", FLATTEN):
        return arr.flatten()
    return arr

def extract_train_features(
    df,
    images_dir: Path,
    *,
    row_limit: int | None = None,
) -> Tuple[np.ndarray, np.ndarray, StandardScaler, str]:
    """Produce (X, y, scaler, preview_md) from a training dataframe."""
    limit = row_limit or ROW_LIMIT
    features, labels = [], []
    for _, row in df.head(limit).iterrows():
        img_path = images_dir / row.get("filename", "")
        arr = load_and_flatten(img_path)
        if arr is not None:
            features.append(arr)
            labels.append(row.get("fresh_weight_total"))
    if not features:
        from sklearn.preprocessing import StandardScaler as _SS  # ensure consistent type
        return np.array([]), np.array([]), _SS(), "### Train Features Preview\n- samples: `0`"
    scaler = StandardScaler()
    X = scaler.fit_transform(features)
    y = np.array(labels)
    preview_md = (
        "### Train Features Preview\n"
        f"- samples: `{X.shape[0]}`\n"
        f"- feature_dim: `{X.shape[1]}`\n"
        f"- y_preview: `{y[:5].tolist()}`\n"
    )
    return X, y, scaler, preview_md


def extract_test_features(
    df,
    images_dir: Path,
    *,
    scaler: StandardScaler | None,
    label_column: str,
    row_limit: int | None = None,
) -> Tuple[np.ndarray, np.ndarray, bool, str]:
    """Produce (X, y, labels_present, preview_md) for test data."""
    limit = row_limit or ROW_LIMIT
    if df.empty:
        return np.array([]), np.array([]), False, "Empty test table"
    features, labels = [], []
    label_present = label_column in df.columns
    for _, row in df.head(limit).iterrows():
        img_path = images_dir / row.get("filename", "")
        arr = load_and_flatten(img_path)
        if arr is not None:
            features.append(arr)
            if label_present:
                labels.append(row.get(label_column))
    X = scaler.transform(features) if scaler is not None else np.array(features)
    y = np.array(labels) if label_present else np.array([])
    preview_md = (
        "### Test Features Preview\n"
        f"- samples: `{X.shape[0]}`\n"
        f"- feature_dim: `{X.shape[1] if X.ndim==2 else 'NA'}`\n"
        f"- labels_present: `{label_present}`\n"
        f"- y_preview: `{y[:5].tolist()}`\n"
    )
    return X, y, label_present, preview_md
