from __future__ import annotations

from prefect.client.orchestration import get_client
from prefect.client.schemas.actions import WorkPoolCreate
from prefect.exceptions import ObjectNotFound


def ensure_work_pool_and_queues(
    *,
    work_pool: str,
    primary_queue: str,
    batch_queue: str | None = None,
) -> None:
    queue_names = [primary_queue]
    if batch_queue and batch_queue not in queue_names:
        queue_names.append(batch_queue)
    with get_client(sync_client=True) as client:
        try:
            client.read_work_pool(work_pool)
        except ObjectNotFound:
            client.create_work_pool(WorkPoolCreate(name=work_pool, type="process"))
        for priority, queue_name in enumerate(queue_names, start=1):
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
