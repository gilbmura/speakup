"""
app/scheduler.py - APScheduler background job for SLA auto-escalation
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
from app.services import run_sla_check


def sla_job():
    """Daily job: escalate issues that have exceeded SLA threshold."""
    db = SessionLocal()
    try:
        run_sla_check(db)
    except Exception as e:
        print(f"[SLA Job ERROR] {e}")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    # Runs every day at 02:00 AM UTC
    scheduler.add_job(sla_job, CronTrigger(hour=2, minute=0), id="sla_check", replace_existing=True)
    scheduler.start()
    print("[Scheduler] SLA check job scheduled (daily at 02:00 UTC)")
    return scheduler
