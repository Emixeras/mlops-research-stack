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


def get_git_commit_hash(repo_root: Path) -> Optional[str]:
    """Get the current git commit hash (short version).
    
    Returns None if not in a git repository or git command fails.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_git_branch(repo_root: Path) -> Optional[str]:
    """Get the current git branch name.
    
    Returns None if not in a git repository or git command fails.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_git_repo_url(repo_root: Path) -> Optional[str]:
    """Get the git remote origin URL.
    
    Returns None if not in a git repository or git command fails.
    """
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_dvc_data_hash(repo_root: Path, dvc_file: str = "data.dvc") -> Optional[str]:
    """Get the MD5 hash from a DVC file, representing the data version.
    
    Args:
        repo_root: Path to the git repository root
        dvc_file: Name of the .dvc file (default: "data.dvc")
    
    Returns:
        MD5 hash from the .dvc file, or None if file doesn't exist or parsing fails
    """
    dvc_path = repo_root / dvc_file
    if not dvc_path.exists():
        return None
    
    try:
        # Parse the .dvc file (YAML format) to extract the md5 hash
        import yaml
        with open(dvc_path, 'r') as f:
            dvc_content = yaml.safe_load(f)
        
        # The md5 hash is typically under 'outs' -> first entry -> 'md5'
        if 'outs' in dvc_content and len(dvc_content['outs']) > 0:
            return dvc_content['outs'][0].get('md5')
        return None
    except Exception:
        return None
