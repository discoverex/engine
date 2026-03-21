from __future__ import annotations

import json
from pathlib import Path

from discoverex.settings import AppSettings

from ..storage_http import upload_bytes
from .presign import prepare_links


def upload_outputs(
    *,
    flow_run_id: str,
    attempt: int,
    local_paths: dict[str, str],
    settings: AppSettings | dict[str, object],
) -> dict[str, str]:
    links = prepare_links(
        flow_run_id=flow_run_id,
        attempt=attempt,
        entries=("stdout", "stderr", "result", "manifest"),
        settings=settings,
    )
    uploaded: dict[str, str] = {}
    for row in links:
        kind = str(row["kind"])
        object_uri = str(row["object_uri"])
        put_url = str(row["url"])
        if kind == "manifest":
            manifest_path = Path(local_paths["result"]).parent / "artifacts.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "flow_run_id": flow_run_id,
                        "attempt": attempt,
                        "artifacts": [
                            {"kind": name, "object_uri": uri}
                            for name, uri in uploaded.items()
                        ],
                    },
                    ensure_ascii=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            upload_bytes(put_url, manifest_path.read_bytes(), settings=settings)
        else:
            upload_bytes(
                put_url,
                Path(local_paths[kind]).read_bytes(),
                settings=settings,
            )
        uploaded[kind] = object_uri
    return uploaded
