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

The worker image embeds the repo source and installs `tracking`, `storage`, and `ml-gpu` extras at build time.
