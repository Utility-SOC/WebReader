from celery import Celery
import os

# Redis URL (default to localhost for now, will differ in Docker)
# In Docker, hostname will be 'redis'
REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "webreader",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['backend.tasks']
)

# Embedded/desktop mode (WEBREADER_EMBEDDED=1) runs tasks in-process with no
# Redis/worker required. Windows local runs keep the same behaviour by default.
_EMBEDDED = os.getenv("WEBREADER_EMBEDDED") == "1" or os.name == 'nt'

celery_app.conf.update(
    result_expires=86400, # 24 hours
    task_serializer='json',
    accept_content=['json'],  # Ignore other content
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_always_eager=_EMBEDDED,
    task_eager_propagates=_EMBEDDED,
)
