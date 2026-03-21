# Fixed Worker Stack

`./bin/cli worker fixed up` starts an always-on embedded engine worker.

Required env:

- `PREFECT_API_URL`
- `PREFECT_WORK_POOL` default `discoverex-fixed`
- `PREFECT_WORK_QUEUE` default `gpu-fixed`
- `CF_ACCESS_CLIENT_ID`
- `CF_ACCESS_CLIENT_SECRET`

Optional env:

- `STORAGE_API_URL`
- `MLFLOW_TRACKING_URI`
- `MLFLOW_S3_ENDPOINT_URL`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `ARTIFACT_BUCKET`
- `DISCOVEREX_SOURCE_ROOT` default `../..`
- `WORKER_RUNTIME_DIR` default `../../runtime/worker`
- `WORKER_MODEL_CACHE_DIR` default `$HOME/.cache/discoverex-models`

The fixed worker mounts only the live source paths needed by the runtime:
`src`, `infra`, `conf`, and `prefect_flow.py`. Runtime state is mounted at
`/var/lib/discoverex`. Model cache is mounted separately at
`/var/lib/discoverex/cache/models`. The image still installs `tracking`,
`storage`, and `ml-gpu` extras at build time.

Diagnostics:

- `./bin/cli worker fixed doctor`
- `./bin/cli worker fixed doctor --json`
