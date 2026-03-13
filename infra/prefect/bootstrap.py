from __future__ import annotations

import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_repo_paths() -> None:
    root = repo_root()
    for path in (root, root / "src"):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
