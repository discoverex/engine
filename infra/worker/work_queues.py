from __future__ import annotations

import os

from prefect.client.orchestration import get_client
from prefect.client.schemas.actions import WorkPoolCreate
from prefect.exceptions import ObjectNotFound


def _queue_priority(env_name: str, default: int) -> int:
    raw = str(os.environ.get(env_name, "")).strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer, got {raw!r}") from exc
    if value < 1:
        raise ValueError(f"{env_name} must be >= 1, got {value}")
    return value


def ensure_work_pool_and_queues(
    *,
    work_pool: str,
    primary_queue: str,
    batch_queue: str | None = None,
) -> None:
    queue_specs: list[tuple[str, int]] = [
        (primary_queue, _queue_priority("PREFECT_PRIMARY_QUEUE_PRIORITY", 1))
    ]
    if batch_queue and batch_queue not in {name for name, _ in queue_specs}:
        queue_specs.append(
            (batch_queue, _queue_priority("PREFECT_BATCH_QUEUE_PRIORITY", 100))
        )
    with get_client(sync_client=True) as client:
        try:
            client.read_work_pool(work_pool)
        except ObjectNotFound:
            client.create_work_pool(WorkPoolCreate(name=work_pool, type="process"))
        for queue_name, priority in queue_specs:
            try:
                queue = client.read_work_queue_by_name(
                    name=queue_name,
                    work_pool_name=work_pool,
                )
                if getattr(queue, "priority", None) != priority:
                    client.update_work_queue(queue.id, priority=priority)
            except ObjectNotFound:
                client.create_work_queue(
                    name=queue_name,
                    work_pool_name=work_pool,
                    priority=priority,
                )
