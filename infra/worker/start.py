from __future__ import annotations

import os
import subprocess
import sys

from infra.worker.client_env import startup_summary


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    env = dict(os.environ)
    summary = startup_summary(env)
    print(
        f"[discoverex-worker] prefect_api_url={summary.prefect_api_url} "
        f"pool={summary.prefect_work_pool} queue={summary.prefect_work_queue} "
        f"cf_access={'enabled' if summary.cf_access_configured else 'disabled'}",
        file=sys.stderr,
    )
    cmd = ["prefect", "worker", "start"]
    if summary.prefect_work_pool:
        cmd.extend(["--pool", summary.prefect_work_pool])
    cmd.extend(args)
    proc = subprocess.run(cmd, env=env, check=False)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
