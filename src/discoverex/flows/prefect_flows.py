from prefect import flow

from discoverex.application.flows import (
    build_inline_job_spec,
    run_engine_job,
    run_engine_job_flow,
)

engine_run_flow = run_engine_job_flow


@flow(name="discoverex-generate", retries=2, retry_delay_seconds=3)
def generate_flow(
    background_asset_ref: str,
    config_name: str = "generate",
    config_dir: str = "conf",
    overrides: list[str] | None = None,
) -> dict[str, object]:
    return run_engine_job(
        build_inline_job_spec(
            command="generate",
            args={"background_asset_ref": background_asset_ref},
            config_name=config_name,
            config_dir=config_dir,
            overrides=overrides,
        )
    )


@flow(name="discoverex-verify", retries=2, retry_delay_seconds=3)
def verify_flow(
    scene_json_path: str,
    config_name: str = "verify",
    config_dir: str = "conf",
    overrides: list[str] | None = None,
) -> dict[str, object]:
    return run_engine_job(
        build_inline_job_spec(
            command="verify",
            args={"scene_json": scene_json_path},
            config_name=config_name,
            config_dir=config_dir,
            overrides=overrides,
        )
    )


@flow(name="discoverex-animate")
def animate_flow(
    scene_json_paths: list[str] | None = None,
    config_name: str = "animate",
    config_dir: str = "conf",
    overrides: list[str] | None = None,
) -> dict[str, object]:
    return run_engine_job(
        build_inline_job_spec(
            command="animate",
            args={"scene_jsons": scene_json_paths or []},
            config_name=config_name,
            config_dir=config_dir,
            overrides=overrides,
        )
    )


__all__ = ["animate_flow", "engine_run_flow", "generate_flow", "verify_flow"]
