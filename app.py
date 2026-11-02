import os
import shutil
import uuid
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Response, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    UPLOADS_DIR, SAMPLE_DATA_DIR, DRAFTS_DIR,
    get_gemini_api_key, set_gemini_api_key,
    SERVER_HOST, SERVER_PORT
)
from database import (
    create_user, authenticate_user, get_user_by_id, update_user_profile,
    save_user_resume, get_user_active_resume, delete_user_resume,
    get_user_tracker_items, get_user_tracker_item, add_user_tracker_item,
    update_user_tracker_item, delete_user_tracker_item, get_user_tracker_stats,
    get_user_scheduler_config, save_user_scheduler_config,
    get_user_gmail_credentials, save_user_gmail_credentials, disconnect_user_gmail,
    save_user_draft, get_user_draft
)
from auth_service import create_access_token, get_current_user, get_optional_user
from resume_parser import parse_resume
from job_searcher import search_jobs
from job_matcher import rank_and_score_jobs
from email_drafter import draft_email_for_job
from gmail_service import (
    get_gmail_status, disconnect_gmail,
    create_gmail_draft, send_gmail_email, generate_eml_content,
    save_client_credentials, update_gmail_profile_name, connect_gmail_app_password
)
from tracker_service import (
    load_tracker, add_tracker_item,
    update_tracker_item, delete_tracker_item, get_tracker_stats
)
from scheduler_service import (
    load_scheduler_config, update_scheduler_config,
    execute_scheduled_search, start_background_scheduler
)

app = FastAPI(title="JobFlow AI — Multi-Tenant AI Job Search & Application Platform", version="2.5.0")

@app.on_event("startup")
async def on_startup():
    start_background_scheduler()

# User-isolated transient memory cache for active search results and live draft state
# Keyed strictly by user_id: USER_SESSIONS[user_id] = { "current_jobs": [...], "drafts": {...} }
USER_SESSIONS: Dict[str, Dict[str, Any]] = {}

def get_user_session(user_id: str) -> Dict[str, Any]:
    """Retrieve or initialize isolated memory workspace for user_id."""
    if user_id not in USER_SESSIONS:
        USER_SESSIONS[user_id] = {
            "current_jobs": [],
            "drafts": {}
        }
    return USER_SESSIONS[user_id]

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = Path("static/index.html")
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>JobFlow AI Backend Running. Static frontend loading...</h1>"

# ============================================================================
# AUTHENTICATION & ACCESS CONTROL ENDPOINTS
# ============================================================================

class RegisterRequest(BaseModel):
    email: str
    password: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""

@app.post("/api/auth/register")
async def register(req: RegisterRequest, response: Response):
    """Register a new user account with strict data isolation."""
    try:
        user = create_user(
            email=req.email,
            password=req.password,
            first_name=req.first_name or "",
            last_name=req.last_name or ""
        )
        token = create_access_token(user["id"], user["email"])
        response.set_cookie(
            key="jobflow_token",
            value=token,
            httponly=True,
            max_age=7 * 86400,
            samesite="lax"
        )
        return {
            "success": True,
            "message": "Account created successfully.",
            "access_token": token,
            "token": token,
            "user": user
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration error: {str(e)}")

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/auth/login")
async def login(req: LoginRequest, response: Response):
    """Authenticate user credentials and issue an isolated session token."""
    user = authenticate_user(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token(user["id"], user["email"])
    response.set_cookie(
        key="jobflow_token",
        value=token,
        httponly=True,
        max_age=7 * 86400,
        samesite="lax"
    )
    return {
        "success": True,
        "message": f"Welcome back, {user.get('first_name') or user['email']}!",
        "access_token": token,
        "token": token,
        "user": user
    }

@app.post("/api/auth/logout")
async def logout(response: Response, current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    """Log out user and clear session cookies & in-memory caches."""
    if current_user and current_user.get("id") in USER_SESSIONS:
        USER_SESSIONS.pop(current_user["id"], None)
        
    response.delete_cookie(key="jobflow_token")
    return {"success": True, "message": "Logged out successfully."}

@app.get("/api/auth/me")
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Retrieve authenticated user's profile and account identity."""
    return {"success": True, "user": current_user}

# ============================================================================
# SYSTEM STATUS & USER PROFILE (STRICTLY ISOLATED)
# ============================================================================

@app.get("/api/status")
async def get_system_status(current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    """
    Returns user-isolated workspace status.
    If not authenticated, returns clean unauthenticated defaults.
    """
    gemini_key = get_gemini_api_key()
    ai_status = {
        "gemini_active": bool(gemini_key),
        "model": "Gemini 2.5 Flash" if gemini_key else "NLP Semantic Matcher"
    }

    if not current_user:
        return {
            "authenticated": False,
            "user": None,
            "gmail": get_gmail_status(None),
            "ai_engine": ai_status,
            "has_resume": False,
            "resume": None,
            "total_jobs_loaded": 0,
            "tracker_stats": {"Total": 0, "Saved": 0, "To Apply": 0, "Draft Created": 0, "Applied": 0, "Interview": 0, "Offer": 0, "Rejected": 0},
            "scheduler": {
                "enabled": False,
                "frequency": "every_6_hours",
                "next_run_time": None,
                "last_run_status": "Not started yet"
            }
        }

    user_id = current_user["id"]
    gmail_stat = get_gmail_status(user_id)
    tracker_stats = get_tracker_stats(user_id)
    active_resume = get_user_active_resume(user_id)
    sched_cfg = load_scheduler_config(user_id)
    session = get_user_session(user_id)

    resume_info = None
    if active_resume:
        resume_info = {
            "file_name": active_resume.get("original_filename"),
            "original_filename": active_resume.get("original_filename"),
            "candidate_name": active_resume.get("name"),
            "email": active_resume.get("email"),
            "skills_count": len(active_resume.get("skills", [])),
            "years_of_experience": active_resume.get("years_of_experience", 0)
        }

    return {
        "authenticated": True,
        "user": current_user,
        "gmail": gmail_stat,
        "ai_engine": ai_status,
        "has_resume": active_resume is not None,
        "resume": resume_info,
        "total_jobs_loaded": len(session["current_jobs"]),
        "tracker_stats": tracker_stats,
        "scheduler": {
            "enabled": sched_cfg.get("enabled", False),
            "frequency": sched_cfg.get("frequency", "every_6_hours"),
            "next_run_time": sched_cfg.get("next_run_time"),
            "last_run_status": sched_cfg.get("last_run_status")
        }
    }

@app.get("/api/user/profile")
async def get_user_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Retrieve profile name strictly for authenticated user."""
    user_id = current_user["id"]
    gmail_status = get_gmail_status(user_id)
    active_resume = get_user_active_resume(user_id)

    first_name = current_user.get("first_name", "") or gmail_status.get("first_name", "")
    last_name = current_user.get("last_name", "") or gmail_status.get("last_name", "")
    full_name = current_user.get("full_name", "") or gmail_status.get("full_name", "")
    email = current_user.get("email", "")

    if not full_name and active_resume:
        resume_name = active_resume.get("name", "")
        if resume_name:
            parts = resume_name.split()
            first_name = parts[0]
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
            full_name = resume_name

    return {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name or f"{first_name} {last_name}".strip(),
        "email": email,
        "connected": gmail_status.get("connected", False),
        "auth_mode": gmail_status.get("auth_mode")
    }

class ProfileUpdateRequest(BaseModel):
    first_name: str
    last_name: str

@app.post("/api/user/profile")
async def update_profile(req: ProfileUpdateRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Update user first and last name for email signature strictly in user's account."""
    user_id = current_user["id"]
    updated_user = update_user_profile(user_id, req.first_name, req.last_name)
    update_gmail_profile_name(req.first_name, req.last_name, user_id=user_id)

    # Refresh candidate name in user's in-memory session drafts
    full_name = updated_user.get("full_name", "")
    session = get_user_session(user_id)
    active_resume = get_user_active_resume(user_id)
    gmail_stat = get_gmail_status(user_id)

    if active_resume and session["current_jobs"]:
        for job in session["current_jobs"]:
            draft = draft_email_for_job(active_resume, job, user_profile=gmail_stat)
            job["email_draft"] = draft
            session["drafts"][job["id"]] = {
                "candidate_name": full_name,
                "draft": draft,
                "status": "Draft Prepared (Unsaved)",
                "gmail_draft_id": None
            }

    return {"success": True, "full_name": full_name, "message": "Profile signature updated successfully."}

# ============================================================================
# RESUME UPLOAD, DOWNLOAD & ISOLATED STORAGE
# ============================================================================

@app.post("/api/resume/upload")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Upload resume in PDF or Word (DOCX) format.
    CRITICAL SECURITY REQUIREMENT:
    1. Stored strictly in user's private upload directory: uploads/<user_id>/...
    2. Associated exclusively with authenticated user_id in database.
    3. Strictly preserves exact original filename for application attachments.
    """
    user_id = current_user["id"]
    orig_name = file.filename
    ext = Path(orig_name).suffix.lower()
    if ext not in [".pdf", ".docx", ".doc", ".txt", ".md"]:
        raise HTTPException(status_code=400, detail="Invalid format. Please upload PDF (.pdf) or Word (.docx) file.")

    # Dedicated isolated storage for this user
    user_upload_dir = UPLOADS_DIR / user_id
    user_upload_dir.mkdir(parents=True, exist_ok=True)

    # Sub-folder per upload to prevent name collisions on disk while preserving exact filename
    upload_token = uuid.uuid4().hex[:8]
    target_dir = user_upload_dir / upload_token
    target_dir.mkdir(parents=True, exist_ok=True)
    save_path = target_dir / orig_name

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        parsed_resume = parse_resume(str(save_path))
        parsed_resume["original_filename"] = orig_name
        parsed_resume["file_name"] = orig_name
        parsed_resume["file_path"] = str(save_path)

        saved_resume = save_user_resume(
            user_id=user_id,
            original_filename=orig_name,
            file_path=str(save_path),
            parsed_data=parsed_resume
        )

        # Clear active memory search results for fresh scoring
        session = get_user_session(user_id)
        session["current_jobs"] = []
        session["drafts"] = {}

        return {
            "success": True,
            "message": f"Successfully loaded and parsed {orig_name}",
            "original_filename": orig_name,
            "resume": saved_resume
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {str(e)}")

@app.get("/api/resume/download")
async def download_resume(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Download active resume for authenticated user only.
    Server verifies that the file belongs to this user.
    """
    user_id = current_user["id"]
    active_resume = get_user_active_resume(user_id)
    if not active_resume or not active_resume.get("file_path"):
        raise HTTPException(status_code=404, detail="No resume uploaded for your account.")

    file_path = Path(active_resume["file_path"])
    # Verify file ownership: path must contain user_id
    if user_id not in str(file_path):
        raise HTTPException(status_code=403, detail="Unauthorized access to resume file.")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Resume file not found on disk.")

    original_filename = active_resume.get("original_filename") or file_path.name
    return FileResponse(
        path=str(file_path),
        filename=original_filename,
        media_type="application/octet-stream"
    )

# ============================================================================
# JOB SEARCH & MULTI-TENANT SCORING
# ============================================================================

class SearchRequest(BaseModel):
    keywords: str = ""
    locations: List[str] = []
    location: str = ""
    work_arrangements: List[str] = []
    remote_only: bool = False
    experience_levels: List[str] = []
    experience_level: str = "All"
    industries: List[str] = []
    industry: str = "All"
    companies: List[str] = []
    sources: List[str] = []
    visa_requirement: str = "any"
    max_results: int = 30
    min_score: int = 30

@app.post("/api/search")
async def execute_job_search(
    req: SearchRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)
):
    """
    Multi-source job search engine.
    If authenticated, scores jobs strictly against user's active resume.
    If unauthenticated, provides exploratory search with relevance scores.
    """
    user_id = current_user["id"] if current_user else None
    active_resume = get_user_active_resume(user_id) if user_id else None
    has_uploaded_resume = active_resume is not None

    user_prof = get_gmail_status(user_id) if user_id else {}
    search_keywords = req.keywords.strip()

    if has_uploaded_resume:
        resume_data = active_resume
    else:
        candidate_name = current_user.get("full_name") or user_prof.get("full_name") or "Candidate" if current_user else "Candidate"
        resume_data = {
            "name": candidate_name,
            "email": user_prof.get("email") or (current_user.get("email") if current_user else "") or "",
            "skills": [k.strip() for k in search_keywords.split(",") if k.strip()] if search_keywords else [],
            "years_of_experience": 3,
            "has_resume": False
        }

    # Consolidate locations
    all_locations = list(req.locations)
    if req.location and req.location.strip() and req.location not in all_locations:
        all_locations.append(req.location.strip())

    # Consolidate work arrangements
    work_arr = list(req.work_arrangements)
    if req.remote_only and "remote" not in [w.lower() for w in work_arr]:
        work_arr.append("remote")

    # Consolidate experience levels
    exp_levels = list(req.experience_levels)
    if req.experience_level and req.experience_level != "All" and req.experience_level not in exp_levels:
        exp_levels.append(req.experience_level)

    # Consolidate industries
    ind_list = list(req.industries)
    if req.industry and req.industry != "All" and req.industry not in ind_list:
        ind_list.append(req.industry)

    if not search_keywords and has_uploaded_resume:
        top_skills = resume_data.get("skills", [])[:3]
        search_keywords = ", ".join(top_skills) if top_skills else ""

    # Fetch raw jobs
    raw_jobs = search_jobs(
        keywords=search_keywords,
        locations=all_locations,
        work_arrangements=work_arr,
        experience_levels=exp_levels,
        industries=ind_list,
        companies=req.companies,
        sources=req.sources,
        visa_requirement=req.visa_requirement,
        max_results=req.max_results
    )

    # Score and rank jobs
    preferences = {
        "locations": all_locations,
        "location": req.location,
        "work_arrangements": work_arr,
        "experience_levels": exp_levels,
        "industries": ind_list,
        "visa_requirement": req.visa_requirement,
        "remote_only": req.remote_only
    }
    ranked_jobs = rank_and_score_jobs(
        resume_data=resume_data,
        jobs=raw_jobs,
        preferences=preferences,
        min_score=req.min_score
    )

    # Generate personalized drafts
    candidate_name = resume_data.get("name", "Candidate")
    if user_prof.get("full_name"):
        candidate_name = user_prof.get("full_name")

    session = get_user_session(user_id or "anonymous")
    for job in ranked_jobs:
        job_id = job["id"]
        existing = session["drafts"].get(job_id)
        if not existing or existing.get("candidate_name") != candidate_name:
            draft = draft_email_for_job(resume_data, job, user_profile=user_prof)
            job["email_draft"] = draft
            job["draft_status"] = "Draft Prepared (Unsaved)"
            session["drafts"][job_id] = {
                "candidate_name": candidate_name,
                "draft": draft,
                "status": "Draft Prepared (Unsaved)",
                "gmail_draft_id": None
            }
        else:
            job["email_draft"] = existing["draft"]
            job["draft_status"] = existing["status"]
            job["gmail_draft_id"] = existing["gmail_draft_id"]

    session["current_jobs"] = ranked_jobs

    return {
        "success": True,
        "total_found": len(ranked_jobs),
        "jobs": ranked_jobs
    }

class DraftUpdateRequest(BaseModel):
    job_id: str
    to_email: str
    subject: str
    body: str

@app.post("/api/draft/update")
async def update_email_draft(req: DraftUpdateRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Save user edits to a draft strictly in user's isolated workspace."""
    user_id = current_user["id"]
    session = get_user_session(user_id)
    
    session["drafts"][req.job_id] = {
        "candidate_name": current_user.get("full_name", "Candidate"),
        "draft": {
            "to_email": req.to_email,
            "subject": req.subject,
            "body": req.body
        },
        "status": "Draft Edited",
        "gmail_draft_id": None
    }

    for j in session["current_jobs"]:
        if j["id"] == req.job_id:
            j["email_draft"] = session["drafts"][req.job_id]["draft"]
            break

    # Persist in user database
    save_user_draft(user_id, req.job_id, session["drafts"][req.job_id]["draft"], status="Draft Edited")

    return {"success": True, "message": "Draft updated in your workspace."}

# ============================================================================
# GMAIL DRAFT & SEND ACTIONS (STRICTLY ISOLATED PER USER)
# ============================================================================

class GmailDraftRequest(BaseModel):
    job_id: str
    to_email: str
    subject: str
    body: str
    attach_resume: bool = True

@app.post("/api/gmail/create-draft")
async def save_to_gmail_drafts(req: GmailDraftRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    OPTION A: Creates an email draft in the authenticated user's Gmail with exact original resume attached.
    STRICT USER PRIVACY: Uses user's isolated credentials and user's isolated resume.
    """
    user_id = current_user["id"]
    resume_data = get_user_active_resume(user_id) or {}
    resume_path = resume_data.get("file_path") if req.attach_resume else None
    original_filename = resume_data.get("original_filename")

    result = create_gmail_draft(
        to_email=req.to_email,
        subject=req.subject,
        body_text=req.body,
        resume_file_path=resume_path,
        original_filename=original_filename,
        user_id=user_id
    )

    if result.get("success"):
        draft_id = result.get("draft_id")
        status_text = f"Draft Created in Gmail (ID: {draft_id[:8]})"
        
        session = get_user_session(user_id)
        if req.job_id in session["drafts"]:
            session["drafts"][req.job_id]["status"] = status_text
            session["drafts"][req.job_id]["gmail_draft_id"] = draft_id

        target_job = next((j for j in session["current_jobs"] if j["id"] == req.job_id), None)
        if target_job:
            target_job["draft_status"] = status_text
            target_job["gmail_draft_id"] = draft_id
            
            # Save or update in user's private Tracker
            add_tracker_item(
                user_id=user_id,
                job_data=target_job,
                status="Draft Created",
                email_status=f"Draft saved to Gmail ({req.to_email})",
                notes=f"Draft created with subject: {req.subject}"
            )

        return {
            "success": True,
            "message": result.get("message"),
            "draft_id": draft_id,
            "draft_url": result.get("draft_url")
        }
    else:
        raise HTTPException(status_code=400, detail=result.get("error"))

class GmailSendRequest(BaseModel):
    job_id: str
    to_email: str
    subject: str
    body: str
    attach_resume: bool = True
    confirm_send: bool = False

@app.post("/api/gmail/send-email")
async def send_application_email(req: GmailSendRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    OPTION B: Send Email Directly.
    CRITICAL: User must explicitly confirm and approve.
    Uses authenticated user's isolated Gmail credentials and exact resume attachment.
    """
    if not req.confirm_send:
        raise HTTPException(status_code=400, detail="Explicit confirmation is required before sending email.")

    if not req.to_email or "@" not in req.to_email:
        raise HTTPException(status_code=400, detail="Valid recipient email is required.")

    user_id = current_user["id"]
    resume_data = get_user_active_resume(user_id) or {}
    resume_path = resume_data.get("file_path") if req.attach_resume else None
    original_filename = resume_data.get("original_filename")

    result = send_gmail_email(
        to_email=req.to_email,
        subject=req.subject,
        body_text=req.body,
        resume_file_path=resume_path,
        original_filename=original_filename,
        user_id=user_id
    )

    if result.get("success"):
        msg_id = result.get("message_id")
        status_text = f"Email Sent Directly ({msg_id[:8]})"
        
        session = get_user_session(user_id)
        if req.job_id in session["drafts"]:
            session["drafts"][req.job_id]["status"] = status_text

        target_job = next((j for j in session["current_jobs"] if j["id"] == req.job_id), None)
        if target_job:
            target_job["draft_status"] = status_text
            
            # Update user's private tracker
            add_tracker_item(
                user_id=user_id,
                job_data=target_job,
                status="Applied",
                email_status=f"Directly sent to {req.to_email}",
                notes=f"Application submitted via direct Gmail send. Subject: {req.subject}"
            )

        return {
            "success": True,
            "message": result.get("message"),
            "message_id": msg_id
        }
    else:
        raise HTTPException(status_code=400, detail=result.get("error"))

@app.post("/api/gmail/batch-draft")
async def batch_save_gmail_drafts(
    min_score: int = Form(70),
    attach_resume: bool = Form(True),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Batch creates drafts in Gmail strictly for authenticated user."""
    user_id = current_user["id"]
    resume_data = get_user_active_resume(user_id)
    if not resume_data:
        raise HTTPException(status_code=400, detail="No resume uploaded for your account.")

    resume_path = resume_data.get("file_path") if attach_resume else None
    original_filename = resume_data.get("original_filename")
    session = get_user_session(user_id)
    qualifying_jobs = [j for j in session["current_jobs"] if j.get("match", {}).get("match_score", 0) >= min_score]

    if not qualifying_jobs:
        return {"success": True, "created_count": 0, "message": f"No jobs found with match score >= {min_score}%."}

    created_count = 0
    errors = []

    for job in qualifying_jobs:
        job_id = job["id"]
        draft_info = session["drafts"].get(job_id, {}).get("draft")
        if not draft_info:
            draft_info = draft_email_for_job(resume_data, job)

        res = create_gmail_draft(
            to_email=draft_info["to_email"],
            subject=draft_info["subject"],
            body_text=draft_info["body"],
            resume_file_path=resume_path,
            original_filename=original_filename,
            user_id=user_id
        )
        if res.get("success"):
            created_count += 1
            draft_id = res.get("draft_id")
            status_text = f"Draft Created in Gmail (ID: {draft_id[:8]})"
            session["drafts"][job_id] = {
                "draft": draft_info,
                "status": status_text,
                "gmail_draft_id": draft_id
            }
            job["draft_status"] = status_text
            job["gmail_draft_id"] = draft_id

            add_tracker_item(
                user_id=user_id,
                job_data=job,
                status="Draft Created",
                email_status=f"Draft saved to Gmail ({draft_info['to_email']})",
                notes="Batch draft created"
            )
        else:
            errors.append(f"{job['title']}: {res.get('error')}")

    return {
        "success": True,
        "created_count": created_count,
        "total_eligible": len(qualifying_jobs),
        "errors": errors,
        "message": f"Successfully created {created_count} drafts in your Gmail account."
    }

# ============================================================================
# USER APPLICATION TRACKER ENDPOINTS (ROW-LEVEL SECURITY)
# ============================================================================

@app.get("/api/tracker")
async def get_tracker(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Retrieve all tracked job applications belonging strictly to the authenticated user."""
    user_id = current_user["id"]
    items = load_tracker(user_id)
    return {"success": True, "count": len(items), "items": items}

@app.get("/api/tracker/stats")
async def get_tracker_summary(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Retrieve count statistics per tracker stage for authenticated user only."""
    user_id = current_user["id"]
    stats = get_tracker_stats(user_id)
    return {"success": True, "stats": stats}

class TrackerAddRequest(BaseModel):
    job_id: Optional[str] = None
    job_title: str
    company: str
    location: Optional[str] = "Not specified"
    salary: Optional[str] = "Competitive"
    application_link: Optional[str] = "#"
    recruiter_email: Optional[str] = ""
    status: Optional[str] = "Saved"
    notes: Optional[str] = ""
    follow_up_date: Optional[str] = ""

@app.post("/api/tracker/add")
async def add_to_tracker(req: TrackerAddRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Add a job to authenticated user's private application tracker."""
    user_id = current_user["id"]
    job_data = {
        "id": req.job_id or str(uuid.uuid4())[:12],
        "title": req.job_title,
        "company": req.company,
        "location": req.location,
        "salary": req.salary,
        "application_link": req.application_link,
        "recruiter_email": req.recruiter_email,
        "match": {"match_score": 0}
    }
    item = add_tracker_item(
        user_id=user_id,
        job_data=job_data,
        status=req.status or "Saved",
        notes=req.notes or "",
        follow_up_date=req.follow_up_date or ""
    )
    return {"success": True, "item": item}

class TrackerUpdateRequest(BaseModel):
    status: Optional[str] = None
    email_status: Optional[str] = None
    notes: Optional[str] = None
    follow_up_date: Optional[str] = None
    recruiter_email: Optional[str] = None
    salary: Optional[str] = None

@app.put("/api/tracker/{item_id}")
async def update_tracker(item_id: str, req: TrackerUpdateRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Update tracked application verifying user ownership."""
    user_id = current_user["id"]
    updates = {k: v for k, v in req.dict().items() if v is not None}
    item = update_tracker_item(user_id, item_id, updates)
    if item:
        return {"success": True, "item": item}
    raise HTTPException(status_code=404, detail="Tracker item not found or unauthorized.")

@app.delete("/api/tracker/{item_id}")
async def remove_from_tracker(item_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Remove a job application from tracker verifying user ownership."""
    user_id = current_user["id"]
    ok = delete_tracker_item(user_id, item_id)
    if ok:
        return {"success": True, "message": "Item deleted from tracker."}
    raise HTTPException(status_code=404, detail="Tracker item not found or unauthorized.")

# ============================================================================
# USER SCHEDULER ENDPOINTS (ISOLATED PER USER)
# ============================================================================

@app.get("/api/scheduler/config")
async def get_scheduler_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Retrieve scheduler configuration and history for authenticated user only."""
    user_id = current_user["id"]
    return {"success": True, "config": load_scheduler_config(user_id)}

class SchedulerConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    frequency: Optional[str] = None
    interval_minutes: Optional[int] = None
    auto_save_tracker: Optional[bool] = None
    auto_create_drafts: Optional[bool] = None
    min_score: Optional[int] = None
    search_preferences: Optional[Dict[str, Any]] = None

@app.post("/api/scheduler/config")
async def save_scheduler_settings(req: SchedulerConfigRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Update scheduler preferences for authenticated user only."""
    user_id = current_user["id"]
    updates = {k: v for k, v in req.dict().items() if v is not None}
    cfg = update_scheduler_config(user_id, updates)
    return {"success": True, "config": cfg}

@app.post("/api/scheduler/run-now")
async def run_scheduler_manually(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Trigger immediate automated search cycle for authenticated user only."""
    user_id = current_user["id"]
    res = await execute_scheduled_search(user_id=user_id, manual=True)
    return res

@app.get("/api/scheduler/logs")
async def get_scheduler_execution_logs(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get history log entries strictly from user's scheduler runs."""
    user_id = current_user["id"]
    cfg = load_scheduler_config(user_id)
    return {"success": True, "logs": cfg.get("logs", [])}

# ============================================================================
# EML, GMAIL WEB & SETTINGS
# ============================================================================

@app.get("/api/draft/download-eml/{job_id}")
async def download_eml(job_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Generate and download .eml file for local email client."""
    user_id = current_user["id"]
    session = get_user_session(user_id)
    job = next((j for j in session["current_jobs"] if j["id"] == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found in your active session.")

    resume_data = get_user_active_resume(user_id) or {}
    draft = session["drafts"].get(job_id, {}).get("draft")
    if not draft:
        draft = draft_email_for_job(resume_data, job)

    resume_path = resume_data.get("file_path")
    original_filename = resume_data.get("original_filename")

    eml_bytes = generate_eml_content(
        to_email=draft["to_email"],
        subject=draft["subject"],
        body_text=draft["body"],
        resume_file_path=resume_path,
        original_filename=original_filename
    )

    clean_title = "".join(c for c in job["title"] if c.isalnum() or c in (" ", "_", "-")).strip()
    filename = f"Draft_{clean_title[:30]}.eml"
    return Response(
        content=eml_bytes,
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

class AppPasswordRequest(BaseModel):
    user_email: str
    app_password: str

@app.post("/api/gmail/connect-app-password")
async def handle_connect_app_password(req: AppPasswordRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Connect Gmail via Google App Password strictly for authenticated user."""
    user_id = current_user["id"]
    import asyncio
    res = await asyncio.to_thread(
        connect_gmail_app_password,
        req.user_email,
        req.app_password,
        current_user.get("first_name", ""),
        current_user.get("last_name", ""),
        user_id
    )
    if res.get("success"):
        return res
    raise HTTPException(status_code=400, detail=res.get("error"))

@app.post("/api/gmail/disconnect")
async def trigger_gmail_disconnect(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Disconnect Gmail strictly for authenticated user."""
    user_id = current_user["id"]
    res = disconnect_gmail(user_id)
    return res

@app.post("/api/settings/credentials")
async def upload_oauth_credentials(file: UploadFile = File(...)):
    """Upload Google Cloud client_secret.json."""
    content = await file.read()
    res = save_client_credentials(content.decode("utf-8"))
    if res.get("success"):
        return res
    raise HTTPException(status_code=400, detail=res.get("error"))

class ApiKeyRequest(BaseModel):
    gemini_api_key: str

@app.post("/api/settings/gemini-key")
async def update_gemini_key(req: ApiKeyRequest):
    """Save Gemini API Key."""
    set_gemini_api_key(req.gemini_api_key)
    return {"success": True, "message": "Gemini API Key updated successfully."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)
