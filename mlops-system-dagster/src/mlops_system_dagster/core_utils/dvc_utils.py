"""Utilities for interacting with DVC inside the Dagster assets.

Encapsulates cache configuration and pulling so asset code stays declarative.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional


def configure_cache(repo_root: Path, *, env: dict | None = None) -> Optional[str]:
    """Configure a custom DVC cache.dir if DVC_CACHE_DIR env or /dvc-cache volume present.

    Returns the configured cache dir (or None if unchanged).
    """
    e = env or os.environ.copy()
    cache_dir = e.get("DVC_CACHE_DIR") or ("/dvc-cache" if os.path.exists("/dvc-cache") else None)
    if not cache_dir:
        return None
    cfg = subprocess.run(
        ["dvc", "config", "cache.dir", cache_dir, "--local"],
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=e,
    )
    if cfg.returncode != 0:
        raise RuntimeError(
            "Failed to set DVC cache.dir"\
            f"\nstdout:\n{cfg.stdout}\nstderr:\n{cfg.stderr}"
        )
    return cache_dir


def dvc_pull(repo_root: Path, *,env: dict | None = None) -> None:
    """Execute `dvc pull` in the repository root, raising on failure."""
    e = env or os.environ.copy()
    result = subprocess.run(
        ["dvc", "pull"], capture_output=True, text=True, cwd=repo_root, env=e
    )
    if result.returncode != 0:
        raise RuntimeError(
            "dvc pull failed"\
            f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
