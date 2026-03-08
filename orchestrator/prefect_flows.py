from __future__ import annotations

from prefect import flow

from discoverex.flows import run_engine_entry


@flow(name="discoverex-generate", retries=2, retry_delay_seconds=3)
def generate_flow(
    background_asset_ref: str,
    config_name: str = "generate",
    config_dir: str = "conf",
    overrides: list[str] | None = None,
) -> dict[str, object]:
    return run_engine_entry(
        command="generate",
        args={"background_asset_ref": background_asset_ref},
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
    )


@flow(name="discoverex-verify", retries=2, retry_delay_seconds=3)
def verify_flow(
    scene_json_path: str,
    config_name: str = "verify",
    config_dir: str = "conf",
    overrides: list[str] | None = None,
) -> dict[str, object]:
    return run_engine_entry(
        command="verify",
        args={"scene_json": scene_json_path},
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
    )


@flow(name="discoverex-animate")
def animate_flow(
    scene_json_paths: list[str] | None = None,
    config_name: str = "animate",
    config_dir: str = "conf",
    overrides: list[str] | None = None,
) -> dict[str, object]:
    return run_engine_entry(
        command="animate",
        args={"scene_jsons": scene_json_paths or []},
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
    )
