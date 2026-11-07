import os
import json
import sqlite3
import hashlib
import secrets
import hmac
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import base64
from cryptography.fernet import Fernet
from config import DATA_DIR, UPLOADS_DIR, AUTH_SECRET_KEY

DB_PATH = DATA_DIR / "jobflow.db"

def _get_credential_cipher():
    """Derive deterministic Fernet AES key from server AUTH_SECRET_KEY."""
    k = hashlib.sha256(AUTH_SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(k))

def encrypt_credential(text: str) -> str:
    """Encrypt sensitive credentials at rest using AES-CBC-HMAC (Fernet)."""
    if not text:
        return ""
    if text.startswith("enc:"):
        return text
    try:
        cipher = _get_credential_cipher()
        return "enc:" + cipher.encrypt(text.encode("utf-8")).decode("utf-8")
    except Exception:
        return text

def decrypt_credential(text: str) -> str:
    """Decrypt sensitive credentials encrypted at rest."""
    if not text:
        return ""
    if text.startswith("enc:"):
        try:
            cipher = _get_credential_cipher()
            return cipher.decrypt(text[4:].encode("utf-8")).decode("utf-8")
        except Exception:
            return ""
    return text

def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with row factory configured."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_password(password: str) -> str:
    """Secure password hashing using PBKDF2-HMAC-SHA256 with 100,000 iterations and random salt."""
    salt = secrets.token_bytes(16)
    iterations = 100_000
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2:sha256:{iterations}${salt.hex()}${key.hex()}"

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hashed string using constant-time comparison."""
    try:
        parts = hashed.split("$")
        if len(parts) != 3:
            return False
        meta, salt_hex, key_hex = parts
        _, _, iterations_str = meta.split(":")
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        computed_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(computed_key, expected_key)
    except Exception:
        return False

def init_db():
    """Initialize database tables with strict user ownership and indexes."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                first_name TEXT DEFAULT '',
                last_name TEXT DEFAULT '',
                full_name TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")

        # 2. User Resumes Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_resumes (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                candidate_name TEXT DEFAULT '',
                candidate_email TEXT DEFAULT '',
                candidate_phone TEXT DEFAULT '',
                years_of_experience REAL DEFAULT 0,
                skills_json TEXT DEFAULT '[]',
                raw_text TEXT DEFAULT '',
                parsed_data_json TEXT DEFAULT '{}',
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_resumes_user ON user_resumes(user_id, is_active)")

        # 3. Application Tracker Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracker_items (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                job_title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT DEFAULT '',
                salary TEXT DEFAULT '',
                work_arrangement TEXT DEFAULT '',
                application_link TEXT DEFAULT '',
                recruiter_name TEXT DEFAULT '',
                recruiter_email TEXT DEFAULT '',
                match_score INTEGER DEFAULT 50,
                status TEXT DEFAULT 'Saved',
                email_status TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                follow_up_date TEXT DEFAULT '',
                applied_date TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracker_user ON tracker_items(user_id, status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracker_user_job ON tracker_items(user_id, job_id)")

        # Migration: ensure tracker_items has new verification and link preservation columns
        cursor.execute("PRAGMA table_info(tracker_items)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        new_columns = [
            ("original_url", "TEXT DEFAULT ''"),
            ("source", "TEXT DEFAULT ''"),
            ("verification_status", "TEXT DEFAULT 'Verified Job'"),
            ("verified_at", "TEXT DEFAULT ''"),
            ("verification_source", "TEXT DEFAULT ''"),
            ("visa_status", "TEXT DEFAULT ''"),
            ("country", "TEXT DEFAULT ''"),
            ("is_apply_disabled", "INTEGER DEFAULT 0"),
            ("apply_status_text", "TEXT DEFAULT ''")
        ]
        for col_name, col_type in new_columns:
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE tracker_items ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass

        # 4. User Scheduler Configuration & Logs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_schedulers (
                user_id TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                frequency TEXT DEFAULT 'every_6_hours',
                interval_minutes INTEGER DEFAULT 360,
                auto_save_tracker INTEGER DEFAULT 1,
                auto_create_drafts INTEGER DEFAULT 0,
                min_score INTEGER DEFAULT 65,
                last_run_time TEXT,
                last_run_status TEXT DEFAULT 'Not started yet',
                next_run_time TEXT,
                total_runs INTEGER DEFAULT 0,
                search_preferences_json TEXT DEFAULT '{}',
                logs_json TEXT DEFAULT '[]',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # 5. User Gmail Credentials & Status Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_gmail_credentials (
                user_id TEXT PRIMARY KEY,
                connected INTEGER DEFAULT 0,
                email TEXT DEFAULT '',
                auth_mode TEXT DEFAULT '',
                app_password TEXT DEFAULT '',
                oauth_token_json TEXT DEFAULT '{}',
                first_name TEXT DEFAULT '',
                last_name TEXT DEFAULT '',
                full_name TEXT DEFAULT '',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # 6. User Job Drafts Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_drafts (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                to_email TEXT DEFAULT '',
                subject TEXT DEFAULT '',
                body TEXT DEFAULT '',
                status TEXT DEFAULT 'Draft Prepared',
                gmail_draft_id TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, job_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_drafts_user ON user_drafts(user_id, job_id)")

        # Security Migration: encrypt any legacy plaintext app_passwords at rest
        try:
            cursor.execute("SELECT user_id, app_password FROM user_gmail_credentials WHERE app_password != '' AND app_password NOT LIKE 'enc:%'")
            unencrypted = cursor.fetchall()
            for row in unencrypted:
                u_id = row[0]
                plain_pwd = row[1]
                enc_pwd = encrypt_credential(plain_pwd)
                cursor.execute("UPDATE user_gmail_credentials SET app_password = ? WHERE user_id = ?", (enc_pwd, u_id))
        except Exception:
            pass

        conn.commit()

# ============================================================================
# USER AUTHENTICATION & MANAGEMENT
# ============================================================================

def create_user(email: str, password: str, first_name: str = "", last_name: str = "") -> Dict[str, Any]:
    """Register a new user with unique ID and hashed password."""
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email:
        raise ValueError("A valid email address is required.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    user_id = f"usr_{secrets.token_hex(8)}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pwd_hash = hash_password(password)
    full_name = f"{first_name.strip()} {last_name.strip()}".strip()

    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (id, email, password_hash, first_name, last_name, full_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, clean_email, pwd_hash, first_name.strip(), last_name.strip(), full_name, now, now))
            
            # Initialize empty scheduler config for this user
            cursor.execute("""
                INSERT INTO user_schedulers (user_id, updated_at)
                VALUES (?, ?)
            """, (user_id, now))
            
            conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError("An account with this email address already exists.")

    return get_user_by_id(user_id)

def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Verify user credentials and return user dict if valid."""
    clean_email = email.strip().lower()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (clean_email,))
        row = cursor.fetchone()
        if not row:
            return None
        if verify_password(password, row["password_hash"]):
            return {
                "id": row["id"],
                "email": row["email"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "full_name": row["full_name"],
                "created_at": row["created_at"]
            }
        return None

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve user details by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, first_name, last_name, full_name, created_at FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Retrieve user details by email."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, first_name, last_name, full_name, created_at FROM users WHERE email = ?", (email.strip().lower(),))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)

def update_user_profile(user_id: str, first_name: str, last_name: str) -> Dict[str, Any]:
    """Update user first and last name."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_name = f"{first_name.strip()} {last_name.strip()}".strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET first_name = ?, last_name = ?, full_name = ?, updated_at = ?
            WHERE id = ?
        """, (first_name.strip(), last_name.strip(), full_name, now, user_id))
        
        # Also update profile name in Gmail credentials table if present
        cursor.execute("""
            UPDATE user_gmail_credentials
            SET first_name = ?, last_name = ?, full_name = ?, updated_at = ?
            WHERE user_id = ?
        """, (first_name.strip(), last_name.strip(), full_name, now, user_id))
        
        conn.commit()
    return get_user_by_id(user_id)

# ============================================================================
# USER RESUME STORAGE & ISOLATION
# ============================================================================

def get_user_upload_dir(user_id: str) -> Path:
    """Return user-isolated upload folder path: uploads/<user_id>/"""
    user_dir = UPLOADS_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir

def save_user_resume(user_id: str, original_filename: str, file_path: str, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save resume details exclusively for this user.
    Deactivates any previous active resume for this user.
    """
    resume_id = f"res_{secrets.token_hex(8)}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    skills_json = json.dumps(parsed_data.get("skills", []))
    parsed_json = json.dumps(parsed_data)

    with get_connection() as conn:
        cursor = conn.cursor()
        # Deactivate previous resumes for this user
        cursor.execute("UPDATE user_resumes SET is_active = 0 WHERE user_id = ?", (user_id,))
        
        cursor.execute("""
            INSERT INTO user_resumes (
                id, user_id, original_filename, file_path,
                candidate_name, candidate_email, candidate_phone,
                years_of_experience, skills_json, raw_text, parsed_data_json,
                is_active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (
            resume_id, user_id, original_filename, file_path,
            parsed_data.get("name", ""), parsed_data.get("email", ""), parsed_data.get("phone", ""),
            float(parsed_data.get("years_of_experience", 0)),
            skills_json, parsed_data.get("raw_text", ""), parsed_json, now
        ))
        conn.commit()

    return get_user_active_resume(user_id)

def get_user_active_resume(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve active resume for the authenticated user only."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM user_resumes WHERE user_id = ? AND is_active = 1
            ORDER BY created_at DESC LIMIT 1
        """, (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        parsed = {}
        try:
            parsed = json.loads(row["parsed_data_json"])
        except Exception:
            pass

        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "original_filename": row["original_filename"],
            "file_name": row["original_filename"],
            "file_path": row["file_path"],
            "name": row["candidate_name"] or parsed.get("name", ""),
            "email": row["candidate_email"] or parsed.get("email", ""),
            "phone": row["candidate_phone"] or parsed.get("phone", ""),
            "years_of_experience": row["years_of_experience"],
            "skills": json.loads(row["skills_json"] or "[]"),
            "raw_text": row["raw_text"],
            "work_experience": parsed.get("work_experience", []),
            "education": parsed.get("education", []),
            "projects": parsed.get("projects", []),
            "created_at": row["created_at"]
        }

def delete_user_resume(user_id: str) -> bool:
    """Delete active resume for this user."""
    active = get_user_active_resume(user_id)
    if active and active.get("file_path"):
        try:
            p = Path(active["file_path"])
            if p.exists() and str(user_id) in str(p):
                p.unlink()
        except Exception:
            pass

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE user_resumes SET is_active = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
    return True

# ============================================================================
# USER APPLICATION TRACKER (ISOLATED PER USER)
# ============================================================================

def get_user_tracker_items(user_id: str, status_filter: str = "All") -> List[Dict[str, Any]]:
    """Retrieve tracked jobs belonging ONLY to the authenticated user."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if status_filter and status_filter != "All":
            cursor.execute("""
                SELECT * FROM tracker_items WHERE user_id = ? AND status = ?
                ORDER BY updated_at DESC
            """, (user_id, status_filter))
        else:
            cursor.execute("""
                SELECT * FROM tracker_items WHERE user_id = ?
                ORDER BY updated_at DESC
            """, (user_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def get_user_tracker_item(user_id: str, item_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve single tracked job verifying strict user ownership."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tracker_items WHERE user_id = ? AND id = ?", (user_id, item_id))
        row = cursor.fetchone()
        return dict(row) if row else None

def add_user_tracker_item(user_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """Add a new application to the user's private tracker."""
    item_id = f"tr_{secrets.token_hex(6)}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tracker_items (
                id, user_id, job_id, job_title, company, location, salary,
                work_arrangement, application_link, original_url, source,
                verification_status, verified_at, verification_source,
                visa_status, country, is_apply_disabled, apply_status_text,
                recruiter_name, recruiter_email,
                match_score, status, email_status, notes, follow_up_date, applied_date,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item_id, user_id, item.get("job_id", ""), item.get("job_title", ""), item.get("company", ""),
            item.get("location", ""), item.get("salary", ""), item.get("work_arrangement", ""),
            item.get("application_link", ""), item.get("original_url") or item.get("application_link", ""),
            item.get("source", ""), item.get("verification_status", "Verified Job"),
            item.get("verified_at", ""), item.get("verification_source", ""),
            item.get("visa_status", ""), item.get("country", ""),
            1 if item.get("is_apply_disabled") else 0, item.get("apply_status_text", ""),
            item.get("recruiter_name", ""), item.get("recruiter_email", ""),
            int(item.get("match_score", 50)), item.get("status", "Saved"), item.get("email_status", "Not Contacted"),
            item.get("notes", ""), item.get("follow_up_date", ""), item.get("applied_date", ""),
            now, now
        ))
        conn.commit()

    return get_user_tracker_item(user_id, item_id)

def update_user_tracker_item(user_id: str, item_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update tracked job enforcing user ownership."""
    existing = get_user_tracker_item(user_id, item_id)
    if not existing:
        return None

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    allowed_keys = [
        "job_title", "company", "location", "salary", "work_arrangement",
        "application_link", "original_url", "source", "verification_status",
        "verified_at", "verification_source", "visa_status", "country",
        "is_apply_disabled", "apply_status_text", "recruiter_name", "recruiter_email",
        "match_score", "status", "email_status", "notes", "follow_up_date", "applied_date"
    ]
    
    set_clauses = ["updated_at = ?"]
    params = [now]

    for k in allowed_keys:
        if k in updates:
            set_clauses.append(f"{k} = ?")
            params.append(updates[k])

    params.extend([user_id, item_id])

    with get_connection() as conn:
        cursor = conn.cursor()
        query = f"UPDATE tracker_items SET {', '.join(set_clauses)} WHERE user_id = ? AND id = ?"
        cursor.execute(query, tuple(params))
        conn.commit()

    return get_user_tracker_item(user_id, item_id)

def delete_user_tracker_item(user_id: str, item_id: str) -> bool:
    """Delete tracked job enforcing user ownership."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tracker_items WHERE user_id = ? AND id = ?", (user_id, item_id))
        conn.commit()
        return cursor.rowcount > 0

def get_user_tracker_stats(user_id: str) -> Dict[str, int]:
    """Calculate application counts per status for the authenticated user."""
    statuses = ["Saved", "To Apply", "Draft Created", "Applied", "Interview", "Offer", "Rejected"]
    stats = {"Total": 0}
    for s in statuses:
        stats[s] = 0

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, COUNT(*) as count FROM tracker_items
            WHERE user_id = ?
            GROUP BY status
        """, (user_id,))
        rows = cursor.fetchall()
        for r in rows:
            st = r["status"]
            cnt = r["count"]
            if st in stats:
                stats[st] = cnt
            stats["Total"] += cnt

    return stats

# ============================================================================
# USER SCHEDULER CONFIGURATION & LOGS (ISOLATED PER USER)
# ============================================================================

def get_user_scheduler_config(user_id: str) -> Dict[str, Any]:
    """Retrieve scheduler configuration and execution history for this user only."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_schedulers WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        default_prefs = {
            "keywords": "",
            "locations": [],
            "work_arrangements": [],
            "experience_levels": [],
            "industries": [],
            "visa_requirement": "any"
        }

        if not row:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO user_schedulers (user_id, updated_at) VALUES (?, ?)
            """, (user_id, now))
            conn.commit()
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
                "search_preferences": default_prefs,
                "logs": []
            }

        try:
            prefs = json.loads(row["search_preferences_json"] or "{}")
        except Exception:
            prefs = default_prefs

        try:
            logs = json.loads(row["logs_json"] or "[]")
        except Exception:
            logs = []

        return {
            "enabled": bool(row["enabled"]),
            "frequency": row["frequency"] or "every_6_hours",
            "interval_minutes": row["interval_minutes"] or 360,
            "auto_save_tracker": bool(row["auto_save_tracker"]),
            "auto_create_drafts": bool(row["auto_create_drafts"]),
            "min_score": row["min_score"] or 65,
            "last_run_time": row["last_run_time"],
            "last_run_status": row["last_run_status"] or "Not started yet",
            "next_run_time": row["next_run_time"],
            "total_runs": row["total_runs"] or 0,
            "search_preferences": prefs,
            "logs": logs
        }

def save_user_scheduler_config(user_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Save scheduler configuration for this user only."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefs_json = json.dumps(config.get("search_preferences", {}))
    logs_json = json.dumps(config.get("logs", []))

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_schedulers (
                user_id, enabled, frequency, interval_minutes,
                auto_save_tracker, auto_create_drafts, min_score,
                last_run_time, last_run_status, next_run_time, total_runs,
                search_preferences_json, logs_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                enabled = excluded.enabled,
                frequency = excluded.frequency,
                interval_minutes = excluded.interval_minutes,
                auto_save_tracker = excluded.auto_save_tracker,
                auto_create_drafts = excluded.auto_create_drafts,
                min_score = excluded.min_score,
                last_run_time = excluded.last_run_time,
                last_run_status = excluded.last_run_status,
                next_run_time = excluded.next_run_time,
                total_runs = excluded.total_runs,
                search_preferences_json = excluded.search_preferences_json,
                logs_json = excluded.logs_json,
                updated_at = excluded.updated_at
        """, (
            user_id,
            1 if config.get("enabled") else 0,
            config.get("frequency", "every_6_hours"),
            int(config.get("interval_minutes", 360)),
            1 if config.get("auto_save_tracker", True) else 0,
            1 if config.get("auto_create_drafts", False) else 0,
            int(config.get("min_score", 65)),
            config.get("last_run_time"),
            config.get("last_run_status", "Not started yet"),
            config.get("next_run_time"),
            int(config.get("total_runs", 0)),
            prefs_json, logs_json, now
        ))
        conn.commit()

    return get_user_scheduler_config(user_id)

# ============================================================================
# USER GMAIL CREDENTIALS & ISOLATION
# ============================================================================

def get_user_gmail_credentials(user_id: str) -> Dict[str, Any]:
    """Retrieve isolated Gmail credentials and profile for this user."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_gmail_credentials WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            # Fallback to user account name
            u = get_user_by_id(user_id)
            return {
                "connected": False,
                "email": None,
                "first_name": u.get("first_name", "") if u else "",
                "last_name": u.get("last_name", "") if u else "",
                "full_name": u.get("full_name", "") if u else "",
                "auth_mode": None,
                "app_password": "",
                "oauth_token": {}
            }

        oauth_token = {}
        try:
            oauth_token = json.loads(row["oauth_token_json"] or "{}")
        except Exception:
            pass

        raw_pwd = row["app_password"] or ""
        decrypted_pwd = decrypt_credential(raw_pwd)

        return {
            "connected": bool(row["connected"]),
            "email": row["email"] or None,
            "first_name": row["first_name"] or "",
            "last_name": row["last_name"] or "",
            "full_name": row["full_name"] or "",
            "auth_mode": row["auth_mode"] or None,
            "app_password": decrypted_pwd,
            "oauth_token": oauth_token
        }

def save_user_gmail_credentials(user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Save isolated Gmail connection for this user (encrypts app_password at rest)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    oauth_json = json.dumps(data.get("oauth_token", {}))
    raw_pwd = data.get("app_password", "")
    stored_pwd = encrypt_credential(raw_pwd) if raw_pwd else ""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_gmail_credentials (
                user_id, connected, email, auth_mode, app_password, oauth_token_json,
                first_name, last_name, full_name, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                connected = excluded.connected,
                email = excluded.email,
                auth_mode = excluded.auth_mode,
                app_password = excluded.app_password,
                oauth_token_json = excluded.oauth_token_json,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                full_name = excluded.full_name,
                updated_at = excluded.updated_at
        """, (
            user_id,
            1 if data.get("connected") else 0,
            data.get("email", ""),
            data.get("auth_mode", ""),
            stored_pwd,
            oauth_json,
            data.get("first_name", ""),
            data.get("last_name", ""),
            data.get("full_name", ""),
            now
        ))
        conn.commit()

    return get_user_gmail_credentials(user_id)

def disconnect_user_gmail(user_id: str) -> bool:
    """Disconnect Gmail for this user only."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_gmail_credentials WHERE user_id = ?", (user_id,))
        conn.commit()
    return True

# ============================================================================
# USER EMAIL DRAFTS (ISOLATED PER USER)
# ============================================================================

def save_user_draft(user_id: str, job_id: str, draft: Dict[str, Any], status: str = "Draft Prepared", gmail_draft_id: Optional[str] = None):
    """Save an email draft strictly for this user."""
    draft_id = f"drf_{secrets.token_hex(6)}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_drafts (
                id, user_id, job_id, to_email, subject, body, status, gmail_draft_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, job_id) DO UPDATE SET
                to_email = excluded.to_email,
                subject = excluded.subject,
                body = excluded.body,
                status = excluded.status,
                gmail_draft_id = excluded.gmail_draft_id,
                updated_at = excluded.updated_at
        """, (
            draft_id, user_id, job_id,
            draft.get("to_email", ""),
            draft.get("subject", ""),
            draft.get("body", ""),
            status, gmail_draft_id, now
        ))
        conn.commit()

def get_user_draft(user_id: str, job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve saved email draft for this user and job."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_drafts WHERE user_id = ? AND job_id = ?", (user_id, job_id))
        row = cursor.fetchone()
        return dict(row) if row else None

# Initialize tables when module is imported
init_db()
