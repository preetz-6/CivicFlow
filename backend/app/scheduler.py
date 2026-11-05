"""APScheduler jobs run in real time; what they compute uses the simulated clock."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

log = logging.getLogger("civicflow.scheduler")
_sched: BackgroundScheduler | None = None
JOBS: list[tuple[str, callable, int]] = []  # (id, fn, every_seconds); modules append in C2/C3


def start() -> None:
    global _sched
    if _sched:
        return
    _sched = BackgroundScheduler(daemon=True, job_defaults={"coalesce": True, "max_instances": 1})
    for job_id, fn, secs in JOBS:
        _sched.add_job(fn, "interval", seconds=secs, id=job_id)
    _sched.start()
    log.info("scheduler started with %d jobs", len(JOBS))


def stop() -> None:
    global _sched
    if _sched:
        _sched.shutdown(wait=False)
        _sched = None
