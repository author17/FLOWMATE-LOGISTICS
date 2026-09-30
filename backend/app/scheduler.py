"""Tiny background job runner (one thread). Jobs: automatic bank sync; due-date reminders and nightly backup are added below."""
import threading, time, traceback
from datetime import datetime
from . import config
from .db import SessionLocal

def _bank_sync():
    from .services.banksync import sync_all
    with SessionLocal() as db: sync_all(db)

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
    def _due():
        with SessionLocal() as db: notify_jobs.due_reminders(db)
    def _mail():
        with SessionLocal() as db: notify_jobs.email_pending(db)
    def _backup():
        from .routers.extras import run_backup
        run_backup()
    register("due_reminders", 6 * 3600, _due); register("email", 300, _mail); register("backup", 24 * 3600, _backup)
    if config.BANK_SYNC_HOURS > 0: register("bank_sync", config.BANK_SYNC_HOURS * 3600, _bank_sync)
    threading.Thread(target=_loop, daemon=True, name="flowmate-scheduler").start()
