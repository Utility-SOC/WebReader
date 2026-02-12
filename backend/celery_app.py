from celery import Celery
import os

# Redis URL (default to localhost for now, will differ in Docker)
# In Docker, hostname will be 'redis'
REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "webreader",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    result_expires=86400, # 24 hours
    task_serializer='json',
    accept_content=['json'],  # Ignore other content
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    # Windows specific (optional, but good for local dev if we were to run it)
    # worker_pool = 'solo' if os.name == 'nt' else 'prefork'
)
