"""Tiny background job runner (one thread). Jobs: automatic bank sync; due-date reminders and nightly backup are added below."""
import threading, time, traceback
from datetime import datetime
from . import config
from .db import SessionLocal

def for_each_business(fn):
    """Run a job once per active business, each in its own database session limited to that business."""
    from sqlalchemy import select
    from . import models
    from .tenancy import use_business
    with SessionLocal() as db0: ids = list(db0.scalars(select(models.Business.id).where(models.Business.active == True)))
    for bid in ids:
        try:
            with SessionLocal() as db: use_business(db, bid); fn(db)
        except Exception: print(f"scheduler: job failed for business {bid}:\n{traceback.format_exc()}")

def _bank_sync():
    from .services.banksync import sync_all
    for_each_business(sync_all)

JOBS = []   # (name, every_seconds, fn)
_last: dict[str, float] = {}

def register(name, every_seconds, fn): JOBS.append((name, every_seconds, fn))

def _loop():
    time.sleep(20)
    while True:
        for name, every, fn in JOBS:
            if time.time() - _last.get(name, 0) >= every:
                _last[name] = time.time()
                try: fn()
                except Exception: print(f"scheduler job {name} failed:\n{traceback.format_exc()}")
        time.sleep(60)

def start():
    if config.DISABLE_SCHEDULER: return
    from .services import notify_jobs
    def _due(): for_each_business(notify_jobs.due_reminders)
    def _mail(): for_each_business(notify_jobs.email_pending)
    def _backup():
        from .routers.extras import run_backup
        run_backup()
    register("due_reminders", 6 * 3600, _due); register("email", 300, _mail); register("backup", 24 * 3600, _backup)
    if config.BANK_SYNC_HOURS > 0: register("bank_sync", config.BANK_SYNC_HOURS * 3600, _bank_sync)
    threading.Thread(target=_loop, daemon=True, name="flowmate-scheduler").start()
