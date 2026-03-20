from __future__ import annotations

import tomllib
from pathlib import Path


def test_wheel_includes_delivery_package() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject_path.open("rb") as handle:
        payload = tomllib.load(handle)

    packages = payload["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]

    assert "delivery" in packages

