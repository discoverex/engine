from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib import parse, request

import typer

app = typer.Typer(
    help="MLflow/MinIO artifact download utilities",
    no_args_is_help=True,
    add_completion=False,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = REPO_ROOT / "infra" / "worker" / ".env.fixed"
_USER_AGENT = "discoverex-artifact-cli/1.0"


@app.command("scene-composites")
def scene_composites(
    scene_id: str = typer.Option(..., "--scene-id", help="Target scene_id"),
    output_dir: Path = typer.Option(
        Path("downloads/scene-composites"),
        "--output-dir",
        file_okay=False,
        dir_okay=True,
        help="Directory to store downloaded composites",
    ),
    env_file: Path = typer.Option(
        DEFAULT_ENV_FILE,
        "--env-file",
        exists=False,
        dir_okay=False,
        help="Optional env file with MLflow/storage credentials",
    ),
) -> None:
    env = _runtime_env(env_file)
    experiment_ids = _active_experiment_ids(env)
    if not experiment_ids:
        typer.secho("No MLflow experiments available.", fg=typer.colors.RED)
        raise typer.Exit(1)
    runs = _search_runs(
        env,
        experiment_ids=experiment_ids,
        filter_string=f"params.scene_id = '{scene_id}'",
    )
    if not runs:
        typer.echo(json.dumps({"scene_id": scene_id, "downloaded": 0}, ensure_ascii=False))
        return
    target_root = output_dir / scene_id
    downloaded = []
    for run in runs:
        run_id = _run_id(run)
        tags = _run_tags(run)
        composite_uri = _composite_uri_for_run(env, tags)
        if not composite_uri:
            continue
        destination = target_root / run_id / "composite.png"
        _download_object_uri(env, composite_uri, destination)
        metadata_path = target_root / run_id / "run.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(run, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        downloaded.append(
            {
                "run_id": run_id,
                "scene_id": scene_id,
                "path": str(destination),
                "object_uri": composite_uri,
            }
        )
    typer.echo(
        json.dumps(
            {"scene_id": scene_id, "downloaded": len(downloaded), "items": downloaded},
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("experiment-runs")
def experiment_runs(
    experiment_id: str = typer.Option(..., "--experiment-id", help="Target MLflow experiment id"),
    output_dir: Path = typer.Option(
        Path("downloads/experiment-runs"),
        "--output-dir",
        file_okay=False,
        dir_okay=True,
        help="Directory to store downloaded run bundles",
    ),
    env_file: Path = typer.Option(
        DEFAULT_ENV_FILE,
        "--env-file",
        exists=False,
        dir_okay=False,
        help="Optional env file with MLflow/storage credentials",
    ),
) -> None:
    env = _runtime_env(env_file)
    runs = _search_runs(env, experiment_ids=[experiment_id], filter_string="")
    target_root = output_dir / experiment_id
    downloaded_runs = []
    for run in runs:
        run_id = _run_id(run)
        tags = _run_tags(run)
        run_dir = target_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text(
            json.dumps(run, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        downloaded_paths = _download_run_bundle(env, tags, run_dir)
        downloaded_runs.append(
            {
                "run_id": run_id,
                "downloaded_files": len(downloaded_paths),
                "dir": str(run_dir),
            }
        )
    typer.echo(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "run_count": len(downloaded_runs),
                "runs": downloaded_runs,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("experiment-by-name")
def experiment_by_name(
    experiment_name: str = typer.Option(
        ...,
        "--experiment-name",
        help="Target MLflow experiment name",
    ),
    env_file: Path = typer.Option(
        DEFAULT_ENV_FILE,
        "--env-file",
        exists=False,
        dir_okay=False,
        help="Optional env file with MLflow/storage credentials",
    ),
) -> None:
    env = _runtime_env(env_file)
    experiment = _get_experiment_by_name(env, experiment_name)
    if not experiment:
        typer.secho(
            json.dumps(
                {
                    "experiment_name": experiment_name,
                    "found": False,
                },
                ensure_ascii=False,
                indent=2,
            ),
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)
    typer.echo(
        json.dumps(
            {
                "experiment_name": experiment_name,
                "found": True,
                "experiment": experiment,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("runs-search")
def runs_search(
    experiment_name: str | None = typer.Option(
        None,
        "--experiment-name",
        help="Target MLflow experiment name",
    ),
    experiment_id: str | None = typer.Option(
        None,
        "--experiment-id",
        help="Target MLflow experiment id",
    ),
    filter_string: str = typer.Option(
        "",
        "--filter",
        help="MLflow run search filter string",
    ),
    max_runs: int = typer.Option(
        20,
        "--max-runs",
        min=1,
        help="Maximum number of runs to print",
    ),
    env_file: Path = typer.Option(
        DEFAULT_ENV_FILE,
        "--env-file",
        exists=False,
        dir_okay=False,
        help="Optional env file with MLflow/storage credentials",
    ),
) -> None:
    if not experiment_name and not experiment_id:
        raise typer.BadParameter(
            "either --experiment-name or --experiment-id is required"
        )
    env = _runtime_env(env_file)
    target_experiment_ids: list[str] = []
    if experiment_id:
        target_experiment_ids.append(experiment_id)
    if experiment_name:
        experiment = _get_experiment_by_name(env, experiment_name)
        if not experiment:
            typer.secho(
                json.dumps(
                    {
                        "experiment_name": experiment_name,
                        "found": False,
                        "runs": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                fg=typer.colors.YELLOW,
            )
            raise typer.Exit(1)
        target_experiment_ids.append(str(experiment.get("experiment_id", "")).strip())
    runs = _search_runs(
        env,
        experiment_ids=[item for item in target_experiment_ids if item],
        filter_string=filter_string,
    )
    typer.echo(
        json.dumps(
            {
                "experiment_name": experiment_name,
                "experiment_ids": [item for item in target_experiment_ids if item],
                "filter": filter_string,
                "run_count": len(runs),
                "runs": [_run_summary(run) for run in runs[:max_runs]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _runtime_env(env_file: Path) -> dict[str, str]:
    env = dict(os.environ)
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            key, value = text.split("=", 1)
            env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def _active_experiment_ids(env: dict[str, str]) -> list[str]:
    response = _mlflow_request(env, "POST", "/api/2.0/mlflow/experiments/search", {"max_results": 5000})
    experiments = response.get("experiments", [])
    if not isinstance(experiments, list):
        return []
    ids: list[str] = []
    for item in experiments:
        if not isinstance(item, dict):
            continue
        experiment_id = str(item.get("experiment_id", "")).strip()
        lifecycle = str(item.get("lifecycle_stage", "")).strip().lower()
        if experiment_id and lifecycle != "deleted":
            ids.append(experiment_id)
    return ids


def _search_runs(
    env: dict[str, str],
    *,
    experiment_ids: list[str],
    filter_string: str,
) -> list[dict[str, Any]]:
    page_token = ""
    runs: list[dict[str, Any]] = []
    while True:
        payload: dict[str, Any] = {
            "experiment_ids": experiment_ids,
            "max_results": 1000,
        }
        if filter_string:
            payload["filter"] = filter_string
        if page_token:
            payload["page_token"] = page_token
        response = _mlflow_request(env, "POST", "/api/2.0/mlflow/runs/search", payload)
        page_runs = response.get("runs", [])
        if isinstance(page_runs, list):
            runs.extend(item for item in page_runs if isinstance(item, dict))
        page_token = str(response.get("next_page_token", "")).strip()
        if not page_token:
            break
    return runs


def _get_experiment_by_name(
    env: dict[str, str], experiment_name: str
) -> dict[str, Any] | None:
    response = _mlflow_request(
        env,
        "GET",
        f"/api/2.0/mlflow/experiments/get-by-name?experiment_name={parse.quote(experiment_name, safe='')}",
        None,
    )
    experiment = response.get("experiment")
    if not isinstance(experiment, dict):
        return None
    return experiment


def _mlflow_request(
    env: dict[str, str],
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    tracking_uri = env.get("MLFLOW_TRACKING_URI", "").strip().rstrip("/")
    if not tracking_uri:
        raise RuntimeError("missing MLFLOW_TRACKING_URI")
    url = f"{tracking_uri}{path}"
    body = (
        json.dumps(payload, ensure_ascii=True).encode("utf-8")
        if payload is not None
        else None
    )
    req = request.Request(url, method=method, data=body, headers=_mlflow_headers(env))
    with request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    decoded = json.loads(text) if text.strip() else {}
    if not isinstance(decoded, dict):
        raise RuntimeError(f"unexpected MLflow response type for path={path}")
    return decoded


def _mlflow_headers(env: dict[str, str]) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }
    cf_id = env.get("CF_ACCESS_CLIENT_ID", "").strip()
    cf_secret = env.get("CF_ACCESS_CLIENT_SECRET", "").strip()
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def _run_id(run: dict[str, Any]) -> str:
    info = run.get("info", {})
    return str(info.get("run_id", "")).strip()


def _run_tags(run: dict[str, Any]) -> dict[str, str]:
    data = run.get("data", {})
    raw_tags = data.get("tags", [])
    tags: dict[str, str] = {}
    if not isinstance(raw_tags, list):
        return tags
    for item in raw_tags:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        value = str(item.get("value", "")).strip()
        if key and value:
            tags[key] = value
    return tags


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    info = run.get("info", {})
    tags = _run_tags(run)
    return {
        "run_id": str(info.get("run_id", "")).strip(),
        "status": str(info.get("status", "")).strip(),
        "start_time": info.get("start_time"),
        "end_time": info.get("end_time"),
        "artifact_uri": str(info.get("artifact_uri", "")).strip(),
        "run_name": tags.get("mlflow.runName", "").strip(),
        "job_name": tags.get("job_name", "").strip(),
    }


def _composite_uri_for_run(env: dict[str, str], tags: dict[str, str]) -> str:
    direct = tags.get("artifact_composite_uri", "").strip()
    if direct:
        return direct
    engine_manifest_uri = tags.get("artifact_engine_manifest_uri", "").strip()
    if not engine_manifest_uri:
        return ""
    manifest = _read_json_object_uri(env, engine_manifest_uri)
    if not isinstance(manifest, dict):
        return ""
    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list):
        return ""
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        if str(item.get("logical_name", "")).strip() == "composite_image":
            return str(item.get("object_uri", "")).strip()
    return ""


def _download_run_bundle(
    env: dict[str, str],
    tags: dict[str, str],
    run_dir: Path,
) -> list[Path]:
    downloaded: list[Path] = []
    for tag_name, filename in (
        ("artifact_stdout_uri", "stdout.log"),
        ("artifact_stderr_uri", "stderr.log"),
        ("artifact_result_uri", "result.json"),
        ("artifact_manifest_uri", "artifacts.json"),
        ("artifact_engine_manifest_uri", "engine-artifacts.json"),
    ):
        object_uri = tags.get(tag_name, "").strip()
        if not object_uri:
            continue
        destination = run_dir / filename
        _download_object_uri(env, object_uri, destination)
        downloaded.append(destination)
    engine_manifest_uri = tags.get("artifact_engine_manifest_uri", "").strip()
    if not engine_manifest_uri:
        return downloaded
    manifest = _read_json_object_uri(env, engine_manifest_uri)
    if not isinstance(manifest, dict):
        return downloaded
    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list):
        return downloaded
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        object_uri = str(item.get("object_uri", "")).strip()
        relative_path = str(item.get("relative_path", "")).strip()
        if not object_uri or not relative_path:
            continue
        destination = run_dir / "engine" / relative_path
        _download_object_uri(env, object_uri, destination)
        downloaded.append(destination)
    return downloaded


def _read_json_object_uri(env: dict[str, str], object_uri: str) -> dict[str, Any] | list[Any]:
    bucket, key = _parse_s3_uri(object_uri)
    payload = _s3_client(env).get_object(Bucket=bucket, Key=key)["Body"].read()
    return json.loads(payload.decode("utf-8"))


def _download_object_uri(env: dict[str, str], object_uri: str, destination: Path) -> None:
    bucket, key = _parse_s3_uri(object_uri)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _s3_client(env).download_file(bucket, key, str(destination))


def _parse_s3_uri(object_uri: str) -> tuple[str, str]:
    parsed = parse.urlparse(object_uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise RuntimeError(f"unsupported object uri: {object_uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def _s3_client(env: dict[str, str]) -> Any:
    try:
        import boto3
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "boto3 is required for artifact downloads. Install with `uv sync --extra storage`."
        ) from exc
    endpoint_url = env.get("MLFLOW_S3_ENDPOINT_URL", "").strip() or env.get(
        "S3_ENDPOINT_URL", ""
    ).strip()
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        aws_access_key_id=env.get("AWS_ACCESS_KEY_ID", "").strip() or None,
        aws_secret_access_key=env.get("AWS_SECRET_ACCESS_KEY", "").strip() or None,
        region_name=env.get("AWS_DEFAULT_REGION", "").strip() or "us-east-1",
    )
