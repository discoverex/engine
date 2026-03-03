from __future__ import annotations

from pathlib import Path


def _src_python_files() -> list[Path]:
    src_root = Path("src/discoverex")
    return [path for path in src_root.rglob("*.py") if path.is_file()]


def test_src_python_files_are_200_lines_or_less() -> None:
    offenders: list[str] = []
    for path in _src_python_files():
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > 200:
            offenders.append(f"{path}:{line_count}")
    assert offenders == []


def test_no_direct_bootstrap_container_import_outside_bootstrap_package() -> None:
    offenders: list[str] = []
    for path in _src_python_files():
        if path.parts[:3] == ("src", "discoverex", "bootstrap"):
            continue
        text = path.read_text(encoding="utf-8")
        if "from discoverex.bootstrap.container import" in text:
            offenders.append(str(path))
    assert offenders == []


def test_no_legacy_package_imports() -> None:
    offenders: list[str] = []
    blocked = (
        "from discoverex.pipelines",
        "import discoverex.pipelines",
        "from discoverex.generation",
        "import discoverex.generation",
        "from discoverex.storage",
        "import discoverex.storage",
        "from discoverex.tracking",
        "import discoverex.tracking",
        "from discoverex.verification",
        "import discoverex.verification",
        "from discoverex.ux",
        "import discoverex.ux",
        "from discoverex.cli",
        "import discoverex.cli",
    )
    for path in _src_python_files():
        text = path.read_text(encoding="utf-8")
        if any(pattern in text for pattern in blocked):
            offenders.append(str(path))
    assert offenders == []


def test_application_layer_does_not_import_infra_packages() -> None:
    offenders: list[str] = []
    blocked = ("import mlflow", "import sqlalchemy", "import boto3", "from prefect")
    for path in Path("src/discoverex/application").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(pattern in text for pattern in blocked):
            offenders.append(str(path))
    assert offenders == []


def test_application_layer_does_not_import_bootstrap_package() -> None:
    offenders: list[str] = []
    blocked = ("from discoverex.bootstrap", "import discoverex.bootstrap")
    for path in Path("src/discoverex/application").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(pattern in text for pattern in blocked):
            offenders.append(str(path))
    assert offenders == []


def test_use_cases_do_not_write_files_directly() -> None:
    offenders: list[str] = []
    for path in Path("src/discoverex/application/use_cases").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if ".write_text(" in text:
            offenders.append(str(path))
    assert offenders == []


def test_legacy_layers_are_removed() -> None:
    removed_paths = (
        Path("src/discoverex/pipelines"),
        Path("src/discoverex/cli"),
        Path("src/discoverex/generation"),
        Path("src/discoverex/storage"),
        Path("src/discoverex/tracking"),
        Path("src/discoverex/verification"),
        Path("src/discoverex/ux"),
    )
    offenders = [str(path) for path in removed_paths if path.exists()]
    assert offenders == []
