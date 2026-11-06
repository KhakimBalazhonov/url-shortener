from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "url_shortener",
    broker=settings.celery_broker_url,
    include=["app.tasks.cleanup", "app.tasks.sync_clicks"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    # Расписание Celery Beat: запускать каждые 30 минут
    beat_schedule={
        "cleanup-expired-links-every-30-minutes": {
            "task": "app.tasks.cleanup_expired_links",
            "schedule": crontab(minute="*/30"),
        },
        "sync-clicks-every-minute": {
            "task": "app.tasks.sync_clicks",
            "schedule": crontab(minute="*/1"),
        },
    },
)
