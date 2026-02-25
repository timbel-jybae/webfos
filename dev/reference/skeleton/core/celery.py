"""
Celery 애플리케이션 설정 + Beat 스케줄.

- Celery 앱 생성 및 공통 설정
- Beat 스케줄 정의 (주기적 작업)
- task 이름은 workers/tasks.py의 @celery_app.task(name=...) 과 반드시 일치해야 함

[실행 방법]
    # Worker 실행
    celery -A core.celery worker --loglevel=info

    # Beat 실행 (주기적 스케줄)
    celery -A core.celery beat --loglevel=info

    # Worker + Beat 동시 (개발용)
    celery -A core.celery worker --beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from core.config import settings


celery_app = Celery(
    settings.PROJECT_NAME,
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND_URL,
)

celery_app.conf.update(
    # 타임존
    timezone="Asia/Seoul",
    enable_utc=True,

    # 태스크 직렬화
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=3600,  # 결과 만료: 1시간

    # 워커 설정
    worker_prefetch_multiplier=1,   # 한 번에 1개씩 가져옴
    task_acks_late=True,            # 처리 완료 후 ACK
    task_reject_on_worker_lost=True,

    # 태스크 자동 발견
    imports=[
        "workers.tasks",
    ],
)

# Beat 스케줄 (주기적 작업)
# task 이름은 workers/tasks.py의 @celery_app.task(name=...) 과 반드시 일치
celery_app.conf.beat_schedule = {
    # --- 예시: 필요에 따라 수정 ---
    # "example-hourly": {
    #     "task": "workers.tasks.task_example",
    #     "schedule": crontab(minute="0"),           # 매시 정각
    # },
    # "example-daily": {
    #     "task": "workers.tasks.task_daily_job",
    #     "schedule": crontab(hour="9", minute="0"), # 매일 9시
    # },
    # "example-interval": {
    #     "task": "workers.tasks.task_periodic",
    #     "schedule": crontab(hour="*/4", minute="15"),  # 4시간마다
    # },
}
