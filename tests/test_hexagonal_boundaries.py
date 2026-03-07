from __future__ import annotations

from pathlib import Path


def test_legacy_modules_do_not_import_models_directly() -> None:
    target_files = [
        Path("src/discoverex/application/use_cases/gen_verify/region_pipeline.py"),
        Path("src/discoverex/application/use_cases/gen_verify/composite_pipeline.py"),
        Path(
            "src/discoverex/application/use_cases/gen_verify/verification_pipeline.py"
        ),
        Path("src/discoverex/application/use_cases/verify_only.py"),
    ]
    for file_path in target_files:
        content = file_path.read_text(encoding="utf-8")
        assert "from discoverex.models import" not in content
