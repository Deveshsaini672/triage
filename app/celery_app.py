import logging

from celery import Celery
from celery.signals import worker_ready

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

celery_app = Celery("triage", broker=settings.redis_broker_url, include=["app.tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,
    # Ack after the task finishes so a crashed worker's task is redelivered.
    # Safe because the task is idempotent (see services.triage._lock_pending_ticket).
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # long-ish tasks: don't hoard messages
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    # Don't let a broker outage hang POST /tickets for long.
    task_publish_retry_policy={
        "max_retries": 2,
        "interval_start": 0,
        "interval_step": 0.2,
        "interval_max": 1,
    },
    beat_schedule={
        "sweep-pending-tickets": {"task": "triage.sweep_pending", "schedule": 60.0},
    },
)


@worker_ready.connect
def _check_config(**_) -> None:
    if not settings.gemini_api_key:
        logger.critical("GEMINI_API_KEY is not set: tickets will stay pending")
