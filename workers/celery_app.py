# Maintainer: Levent Çelik — https://github.com/levend18
import os

from celery import Celery

app = Celery(
    "adapter", broker=os.environ.get("REDIS_URL", "redis://redis:6379/0"), include=["workers.tasks"]
)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    worker_concurrency=1,
    worker_max_tasks_per_child=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "poll-banks": {
            "task": "workers.tasks.poll",
            "schedule": float(os.environ.get("POLL_INTERVAL_SECONDS", "30")),
        }
    },
)
