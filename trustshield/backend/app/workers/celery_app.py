from celery import Celery

celery_app = Celery(
    "trustshield",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0",
    include=["app.services.graph.risk_propagation"]
)

celery_app.conf.beat_schedule = {
    "propagate-risk-every-6-hours": {
        "task": "app.services.graph.risk_propagation.propagate_task",
        "schedule": 21600.0, # 6 hours
    },
}
