import os
import json
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

from config import SCHEDULER_FILE, UPLOADS_DIR
import database
from tracker_service import add_tracker_item

FREQUENCY_MINUTES = {
    "every_1_hour": 60,
    "every_2_hours": 120,
    "every_4_hours": 240,
    "every_6_hours": 360,
    "every_12_hours": 720,
    "daily_24_hours": 1440
}

def load_scheduler_config(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Load scheduler settings strictly for the authenticated user."""
    if not user_id:
        return {
            "enabled": False,
            "frequency": "every_6_hours",
            "interval_minutes": 360,
            "auto_save_tracker": True,
            "auto_create_drafts": False,
            "min_score": 65,
            "last_run_time": None,
            "last_run_status": "Not started yet",
            "next_run_time": None,
            "total_runs": 0,
            "search_preferences": {
                "keywords": "",
                "locations": [],
                "work_arrangements": [],
                "experience_levels": [],
                "industries": [],
                "visa_requirement": "any"
            },
            "logs": []
        }
    return database.get_user_scheduler_config(user_id)

def update_scheduler_config(user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update scheduler preferences for the specified user."""
    cfg = database.get_user_scheduler_config(user_id)
    
    for k, v in updates.items():
        if k == "frequency":
            cfg["frequency"] = v
            cfg["interval_minutes"] = FREQUENCY_MINUTES.get(v, cfg.get("interval_minutes", 360))
        elif k == "search_preferences":
            cfg["search_preferences"] = {**cfg.get("search_preferences", {}), **v}
        elif k != "logs":
            cfg[k] = v

    if cfg.get("enabled"):
        mins = cfg.get("interval_minutes", 360)
        next_dt = datetime.now() + timedelta(minutes=mins)
        cfg["next_run_time"] = next_dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        cfg["next_run_time"] = None

    return database.save_user_scheduler_config(user_id, cfg)

async def execute_scheduled_search(user_id: str, manual: bool = False) -> Dict[str, Any]:
    """
    Executes an automated job search cycle strictly for the specified user:
    1. Fetches candidate's active resume from user-isolated database/storage.
    2. Runs multi-source search using saved user preferences.
    3. Calculates match scores.
    4. Automatically saves top matches to the user's private Tracker.
    5. Records execution in user-isolated logs.
    """
    from job_searcher import search_jobs
    from job_matcher import rank_and_score_jobs
    from email_drafter import draft_email_for_job
    from gmail_service import get_gmail_status, create_gmail_draft

    cfg = database.get_user_scheduler_config(user_id)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 1. Resolve Candidate Resume strictly from user's isolated account
    resume_data = database.get_user_active_resume(user_id)
    if not resume_data:
        log_entry = {
            "timestamp": now_str,
            "trigger": "Manual Trigger" if manual else "Automated Schedule",
            "jobs_evaluated": 0,
            "matches_found": 0,
            "drafts_created": 0,
            "status": "Skipped",
            "summary": "No active resume uploaded for this account. Please upload a resume first."
        }
        cfg["logs"] = [log_entry] + (cfg.get("logs", []))[:19]
        cfg["last_run_time"] = now_str
        cfg["last_run_status"] = "Skipped: No active resume uploaded."
        database.save_user_scheduler_config(user_id, cfg)
        return {"success": False, "message": "No active resume uploaded for this account.", "log": log_entry}

    # 2. Extract user search preferences
    prefs = cfg.get("search_preferences", {})
    keywords = prefs.get("keywords") or ", ".join((resume_data.get("skills") or [])[:3]) or "Software Engineer"
    locations = prefs.get("locations", [])
    work_arrangements = prefs.get("work_arrangements", [])
    experience_levels = prefs.get("experience_levels", [])
    industries = prefs.get("industries", [])
    visa_req = prefs.get("visa_requirement", "any")
    min_score = cfg.get("min_score", 65)

    # 3. Execute search
    try:
        raw_jobs = search_jobs(
            keywords=keywords,
            locations=locations,
            work_arrangements=work_arrangements,
            experience_levels=experience_levels,
            industries=industries,
            visa_requirement=visa_req,
            max_results=30
        )
    except Exception as e:
        raw_jobs = []

    # 4. Rank and score jobs against user's resume
    ranked_jobs = rank_and_score_jobs(
        resume_data=resume_data,
        jobs=raw_jobs,
        preferences=prefs,
        min_score=min_score
    )

    matches_found = len(ranked_jobs)
    drafts_created = 0

    # 5. Process matches for this user only
    gmail_stat = get_gmail_status(user_id)
    user_prof = {
        "full_name": resume_data.get("name") or gmail_stat.get("full_name") or "Candidate",
        "email": gmail_stat.get("email") or resume_data.get("email") or ""
    }

    for job in ranked_jobs:
        score = job.get("match", {}).get("match_score", 50)
        
        # Auto-save to user's private Tracker
        if cfg.get("auto_save_tracker", True):
            add_tracker_item(
                user_id=user_id,
                job_data=job,
                status="Saved",
                email_status="Scheduled Match",
                notes=f"Auto-saved by Scheduler. Score: {score}%. {job.get('match', {}).get('why_relevant', '')[:80]}"
            )

        # Auto-create Gmail drafts if configured and Gmail is connected for this user
        if cfg.get("auto_create_drafts") and gmail_stat.get("connected") and score >= 75:
            draft_info = draft_email_for_job(resume_data, job, user_profile=user_prof)
            resume_path = resume_data.get("file_path")
            orig_filename = resume_data.get("original_filename")
            
            res = create_gmail_draft(
                to_email=draft_info.get("to_email", "hiring@company.com"),
                subject=draft_info.get("subject", f"Application: {job['title']}"),
                body_text=draft_info.get("body", ""),
                resume_file_path=resume_path,
                original_filename=orig_filename,
                user_id=user_id
            )
            if res.get("success"):
                drafts_created += 1

    # 6. Update user's scheduler logs & status in database
    status_summary = f"Evaluated {len(raw_jobs)} jobs. Found {matches_found} matching roles (>= {min_score}%)."
    if drafts_created > 0:
        status_summary += f" Created {drafts_created} Gmail drafts."

    log_entry = {
        "timestamp": now_str,
        "trigger": "Manual Trigger" if manual else "Automated Schedule",
        "jobs_evaluated": len(raw_jobs),
        "matches_found": matches_found,
        "drafts_created": drafts_created,
        "status": "Success",
        "summary": status_summary
    }

    cfg["logs"] = [log_entry] + (cfg.get("logs", []))[:19]
    cfg["last_run_time"] = now_str
    cfg["last_run_status"] = status_summary
    cfg["total_runs"] = cfg.get("total_runs", 0) + 1

    if cfg.get("enabled"):
        mins = cfg.get("interval_minutes", 360)
        next_dt = datetime.now() + timedelta(minutes=mins)
        cfg["next_run_time"] = next_dt.strftime("%Y-%m-%d %H:%M:%S")

    database.save_user_scheduler_config(user_id, cfg)

    return {
        "success": True,
        "summary": status_summary,
        "matches_found": matches_found,
        "drafts_created": drafts_created,
        "log": log_entry
    }

_SCHEDULER_RUNNING = False

def start_background_scheduler():
    """Start asynchronous loop that checks active user schedulers without blocking."""
    global _SCHEDULER_RUNNING
    if _SCHEDULER_RUNNING:
        return
    _SCHEDULER_RUNNING = True

    async def _scheduler_loop():
        while True:
            try:
                await asyncio.sleep(60)  # Check every 60 seconds
                now = datetime.now()
                with database.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT user_id, next_run_time FROM user_schedulers WHERE enabled = 1")
                    active_users = cursor.fetchall()

                for row in active_users:
                    u_id = row["user_id"]
                    next_run_str = row["next_run_time"]
                    if next_run_str:
                        try:
                            next_dt = datetime.strptime(next_run_str, "%Y-%m-%d %H:%M:%S")
                            if now >= next_dt:
                                asyncio.create_task(execute_scheduled_search(user_id=u_id, manual=False))
                        except Exception:
                            pass
            except Exception as e:
                print(f"Background scheduler error: {e}")
                await asyncio.sleep(60)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_scheduler_loop())
        else:
            loop.create_task(_scheduler_loop())
    except Exception as e:
        print(f"Could not attach background scheduler task: {e}")
