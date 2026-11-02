import os
import json
import base64
import time
import mimetypes
import imaplib
import smtplib
from pathlib import Path
from email.message import EmailMessage
from typing import Dict, Any, Optional
from urllib.parse import quote

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from config import GMAIL_CREDENTIALS_FILE, GMAIL_TOKEN_FILE, GMAIL_SCOPES, TOKENS_DIR
import database

def get_user_token_file(user_id: str) -> Path:
    """Return isolated OAuth token file path for user: tokens/<user_id>/gmail_token.json"""
    user_token_dir = TOKENS_DIR / user_id
    user_token_dir.mkdir(parents=True, exist_ok=True)
    return user_token_dir / "gmail_token.json"

def get_gmail_web_compose_url(to_email: str, subject: str, body_text: str) -> str:
    """Generate direct 1-click URL that opens Gmail Web with pre-filled draft."""
    return f"https://mail.google.com/mail/?view=cm&fs=1&to={quote(to_email)}&su={quote(subject)}&body={quote(body_text)}"

def get_gmail_status(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Check if Gmail is connected for the specific user and return account details."""
    if not user_id:
        return {
            "connected": False,
            "email": None,
            "first_name": "",
            "last_name": "",
            "full_name": "",
            "auth_mode": None,
            "credentials_configured": GMAIL_CREDENTIALS_FILE.exists()
        }

    # Fetch user's isolated credentials from database
    user_creds = database.get_user_gmail_credentials(user_id)
    if user_creds.get("connected"):
        return {
            "connected": True,
            "email": user_creds.get("email"),
            "first_name": user_creds.get("first_name", ""),
            "last_name": user_creds.get("last_name", ""),
            "full_name": user_creds.get("full_name", ""),
            "auth_mode": user_creds.get("auth_mode"),
            "credentials_configured": True
        }

    # Check user-isolated OAuth token file
    token_file = get_user_token_file(user_id)
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), GMAIL_SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_file, "w", encoding="utf-8") as token_out:
                    token_out.write(creds.to_json())
                    
            if creds and creds.valid:
                service = build("gmail", "v1", credentials=creds)
                profile = service.users().getProfile(userId="me").execute()
                email = profile.get("emailAddress")

                u = database.get_user_by_id(user_id)
                first_name = u.get("first_name", "") if u else ""
                last_name = u.get("last_name", "") if u else ""
                full_name = u.get("full_name", "") if u else ""

                database.save_user_gmail_credentials(user_id, {
                    "connected": True,
                    "email": email,
                    "auth_mode": "oauth",
                    "first_name": first_name,
                    "last_name": last_name,
                    "full_name": full_name
                })

                return {
                    "connected": True,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "full_name": full_name or f"{first_name} {last_name}".strip(),
                    "auth_mode": "oauth",
                    "credentials_configured": True
                }
        except Exception as e:
            print(f"Error checking Gmail OAuth status for user {user_id}: {e}")

    u = database.get_user_by_id(user_id)
    return {
        "connected": False,
        "email": None,
        "first_name": u.get("first_name", "") if u else "",
        "last_name": u.get("last_name", "") if u else "",
        "full_name": u.get("full_name", "") if u else "",
        "auth_mode": None,
        "credentials_configured": GMAIL_CREDENTIALS_FILE.exists()
    }

def update_gmail_profile_name(first_name: str, last_name: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Save or update user's confirmed first and last name."""
    clean_first = first_name.strip()
    clean_last = last_name.strip()
    full_name = f"{clean_first} {clean_last}".strip()
    
    if user_id:
        database.update_user_profile(user_id, clean_first, clean_last)
    return {"success": True, "first_name": clean_first, "last_name": clean_last, "full_name": full_name}

def remove_existing_gmail_session(user_id: Optional[str] = None) -> bool:
    """
    CRITICAL USER DATA ISOLATION:
    Remove Gmail credentials ONLY for the specified user.
    Never deletes or affects any other user's session.
    """
    if not user_id:
        return True
    try:
        database.disconnect_user_gmail(user_id)
        token_file = get_user_token_file(user_id)
        if token_file.exists():
            token_file.unlink(missing_ok=True)
        return True
    except Exception as e:
        print(f"Error removing Gmail session for user {user_id}: {e}")
        return False

def connect_gmail_app_password(
    user_email: str,
    app_password: str,
    first_name: str = "",
    last_name: str = "",
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Connect Gmail using Google App Password (IMAP/SMTP SSL).
    Saves isolated credentials exclusively for user_id.
    """
    if not user_id:
        return {"success": False, "error": "Authentication required to connect Gmail."}

    # Remove previous session for this user only
    remove_existing_gmail_session(user_id)

    clean_email = user_email.strip()
    clean_pass = app_password.replace(" ", "").strip()
    
    if not clean_email or "@" not in clean_email:
        return {"success": False, "error": "Please provide a valid Gmail address."}
    if not clean_pass:
        return {"success": False, "error": "Please provide your 16-character Google App Password."}
        
    try:
        # Test IMAP connection
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(clean_email, clean_pass)
        mail.logout()
        
        # Test SMTP connection
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(clean_email, clean_pass)
        server.quit()
        
        # Determine names
        if not first_name:
            import re
            parts = re.split(r"[._0-9-]", clean_email.split("@")[0])
            clean_parts = [p.capitalize() for p in parts if len(p) >= 2 and p.isalpha()]
            if len(clean_parts) >= 2:
                first_name = clean_parts[0]
                last_name = clean_parts[1]
            elif len(clean_parts) == 1:
                first_name = clean_parts[0]

        full_name = f"{first_name.strip()} {last_name.strip()}".strip()

        # Save to database strictly for this user
        database.save_user_gmail_credentials(user_id, {
            "connected": True,
            "email": clean_email,
            "auth_mode": "app_password",
            "app_password": clean_pass,
            "first_name": first_name.strip(),
            "last_name": last_name.strip(),
            "full_name": full_name
        })

        return {
            "success": True,
            "message": f"Successfully connected Gmail for {clean_email}!",
            "email": clean_email,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name
        }
    except Exception as e:
        error_msg = str(e)
        if "AuthenticationFailed" in error_msg or "Username and Password not accepted" in error_msg:
            return {
                "success": False,
                "error": "Gmail authentication failed. Please verify your 16-character Google App Password."
            }
        return {"success": False, "error": f"Failed to connect to Gmail: {error_msg}"}

def disconnect_gmail(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Disconnect Gmail for the specified user."""
    if not user_id:
        return {"success": True}
    remove_existing_gmail_session(user_id)
    return {"success": True, "message": "Gmail account disconnected successfully."}

def build_email_message(
    sender_email: str,
    to_email: str,
    subject: str,
    body_text: str,
    resume_file_path: Optional[str] = None,
    original_filename: Optional[str] = None
) -> EmailMessage:
    """
    Constructs a standard MIME email message.
    CRITICAL REQUIREMENT: Strictly preserves the exact original resume filename.
    """
    msg = EmailMessage()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body_text)

    # Attach resume if path provided
    if resume_file_path and os.path.exists(resume_file_path):
        attachment_name = original_filename if original_filename else os.path.basename(resume_file_path)
        mime_type, _ = mimetypes.guess_type(resume_file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"
        maintype, subtype = mime_type.split("/", 1)

        with open(resume_file_path, "rb") as f:
            file_data = f.read()

        msg.add_attachment(
            file_data,
            maintype=maintype,
            subtype=subtype,
            filename=attachment_name
        )

    return msg

# --- OPTION A: DRAFT EMAIL IN GMAIL ---
def create_gmail_draft(
    to_email: str,
    subject: str,
    body_text: str,
    resume_file_path: Optional[str] = None,
    original_filename: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    OPTION A: Creates an email draft in Gmail for the authenticated user.
    Attaches resume using EXACT original filename.
    NEVER sends the email.
    """
    status = get_gmail_status(user_id)
    if not status.get("connected"):
        return {
            "success": False,
            "error": "Gmail is not connected for your account. Please connect Gmail in Settings."
        }

    user_email = status.get("email")

    # 1. App Password IMAP Draft Creation
    if status.get("auth_mode") == "app_password":
        try:
            creds = database.get_user_gmail_credentials(user_id)
            app_password = creds.get("app_password")

            msg = build_email_message(
                sender_email=user_email,
                to_email=to_email,
                subject=subject,
                body_text=body_text,
                resume_file_path=resume_file_path,
                original_filename=original_filename
            )

            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(user_email, app_password)

            drafts_folder = '[Gmail]/Drafts'
            try:
                s_code, folders = mail.list()
                if s_code == "OK":
                    for f_entry in folders:
                        f_str = f_entry.decode("utf-8", errors="ignore")
                        if r"\Drafts" in f_str:
                            parts = f_str.split(' "/" ')
                            if len(parts) > 1:
                                drafts_folder = parts[1].strip('"')
                                break
            except Exception:
                pass

            mail.append(drafts_folder, r"(\Draft \Seen)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
            mail.logout()

            return {
                "success": True,
                "draft_id": f"imap_{int(time.time())}",
                "draft_url": "https://mail.google.com/mail/u/0/#drafts",
                "message": f"Draft saved in Gmail Drafts folder with attachment '{original_filename or 'resume'}'."
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to save draft via IMAP: {str(e)}"}

    # 2. OAuth Draft Creation
    token_file = get_user_token_file(user_id)
    if not token_file.exists():
        return {"success": False, "error": "Gmail OAuth token not found for your account."}

    try:
        creds = Credentials.from_authorized_user_file(str(token_file), GMAIL_SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "w", encoding="utf-8") as token_out:
                token_out.write(creds.to_json())
                
        if not creds or not creds.valid:
            return {"success": False, "error": "Gmail credentials expired. Please re-authenticate."}
            
        service = build("gmail", "v1", credentials=creds)
        msg = build_email_message(
            sender_email=user_email,
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            resume_file_path=resume_file_path,
            original_filename=original_filename
        )
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        
        draft = service.users().drafts().create(
            userId="me",
            body={"message": {"raw": raw_message}}
        ).execute()
        
        draft_id = draft.get("id")
        return {
            "success": True,
            "draft_id": draft_id,
            "draft_url": "https://mail.google.com/mail/u/0/#drafts",
            "message": f"Draft created in Gmail Drafts with attachment '{original_filename or 'resume'}'."
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to create draft in Gmail: {str(e)}"}

# --- OPTION B: SEND EMAIL DIRECTLY ---
def send_gmail_email(
    to_email: str,
    subject: str,
    body_text: str,
    resume_file_path: Optional[str] = None,
    original_filename: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    OPTION B: Sends the application email directly through Gmail for the authenticated user.
    CRITICAL: Only called upon explicit user review and approval in UI.
    Attaches resume using EXACT original filename.
    """
    status = get_gmail_status(user_id)
    if not status.get("connected"):
        return {
            "success": False,
            "error": "Gmail is not connected for your account. Please connect your Gmail account via App Password or OAuth."
        }

    user_email = status.get("email")

    # 1. App Password SMTP Direct Send
    if status.get("auth_mode") == "app_password":
        try:
            creds = database.get_user_gmail_credentials(user_id)
            app_password = creds.get("app_password")

            msg = build_email_message(
                sender_email=user_email,
                to_email=to_email,
                subject=subject,
                body_text=body_text,
                resume_file_path=resume_file_path,
                original_filename=original_filename
            )

            server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
            server.login(user_email, app_password)
            server.send_message(msg)
            server.quit()

            return {
                "success": True,
                "message_id": f"smtp_{int(time.time())}",
                "message": f"Application email sent directly to {to_email} with resume '{original_filename or 'resume'}' attached!"
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to send email via SMTP: {str(e)}"}

    # 2. OAuth Direct Send
    token_file = get_user_token_file(user_id)
    if not token_file.exists():
        return {"success": False, "error": "Gmail OAuth token not found for your account."}

    try:
        creds = Credentials.from_authorized_user_file(str(token_file), GMAIL_SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "w", encoding="utf-8") as token_out:
                token_out.write(creds.to_json())
                
        if not creds or not creds.valid:
            return {"success": False, "error": "Gmail credentials expired. Please re-authenticate."}
            
        service = build("gmail", "v1", credentials=creds)
        msg = build_email_message(
            sender_email=user_email,
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            resume_file_path=resume_file_path,
            original_filename=original_filename
        )
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        
        sent = service.users().messages().send(
            userId="me",
            body={"raw": raw_message}
        ).execute()
        
        return {
            "success": True,
            "message_id": sent.get("id"),
            "message": f"Application email sent directly to {to_email} with resume '{original_filename or 'resume'}' attached!"
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to send email via Gmail API: {str(e)}"}

def generate_eml_content(
    to_email: str,
    subject: str,
    body_text: str,
    resume_file_path: Optional[str] = None,
    original_filename: Optional[str] = None
) -> bytes:
    """Generate standard .eml file content preserving exact original resume filename."""
    msg = build_email_message(
        sender_email="user@gmail.com",
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        resume_file_path=resume_file_path,
        original_filename=original_filename
    )
    return msg.as_bytes()

def connect_gmail_oauth():
    pass

def save_client_credentials(client_id: str, client_secret: str) -> bool:
    data = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }
    with open(GMAIL_CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return True
