from typing import List, Dict, Any, Optional
from database import (
    get_user_tracker_items,
    get_user_tracker_item,
    add_user_tracker_item,
    update_user_tracker_item,
    delete_user_tracker_item,
    get_user_tracker_stats
)

VALID_STATUSES = [
    "Saved",
    "To Apply",
    "Draft Created",
    "Applied",
    "Interview",
    "Offer",
    "Rejected"
]

def load_tracker(user_id: str, status_filter: str = "All") -> List[Dict[str, Any]]:
    """Load tracked jobs strictly for the specified user."""
    return get_user_tracker_items(user_id, status_filter)

def add_tracker_item(
    user_id: str,
    job_data: Dict[str, Any],
    status: str = "Saved",
    email_status: str = "Not Contacted",
    notes: str = "",
    follow_up_date: str = ""
) -> Dict[str, Any]:
    """Add or update a job in the user's private application tracker."""
    existing_items = get_user_tracker_items(user_id)
    job_id = job_data.get("id") or job_data.get("job_id", "")
    
    # Check if job already tracked for this user
    for item in existing_items:
        if item.get("job_id") == job_id or (
            item.get("job_title", "").lower() == job_data.get("title", "").lower() and
            item.get("company", "").lower() == job_data.get("company", "").lower()
        ):
            updates = {}
            if status in VALID_STATUSES:
                updates["status"] = status
            if email_status:
                updates["email_status"] = email_status
            if notes:
                updates["notes"] = notes
            if follow_up_date:
                updates["follow_up_date"] = follow_up_date
            return update_user_tracker_item(user_id, item["id"], updates) or item

    new_item_data = {
        "job_id": job_id,
        "job_title": job_data.get("title") or job_data.get("job_title", "Unknown Role"),
        "company": job_data.get("company", "Unknown Company"),
        "location": job_data.get("location", "Not specified"),
        "salary": job_data.get("salary", "Competitive"),
        "work_arrangement": "Remote" if job_data.get("is_remote") else "Onsite / Hybrid",
        "application_link": job_data.get("application_link", "#"),
        "recruiter_name": job_data.get("recruiter_name", ""),
        "recruiter_email": job_data.get("recruiter_email", ""),
        "match_score": job_data.get("match", {}).get("match_score", job_data.get("match_score", 50)),
        "status": status if status in VALID_STATUSES else "Saved",
        "email_status": email_status,
        "notes": notes,
        "follow_up_date": follow_up_date,
        "applied_date": ""
    }
    return add_user_tracker_item(user_id, new_item_data)

def update_tracker_item(user_id: str, item_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update tracked job enforcing user ownership."""
    return update_user_tracker_item(user_id, item_id, updates)

def delete_tracker_item(user_id: str, item_id: str) -> bool:
    """Delete tracked job enforcing user ownership."""
    return delete_user_tracker_item(user_id, item_id)

def get_tracker_stats(user_id: str) -> Dict[str, int]:
    """Calculate isolated tracker statistics for this user."""
    return get_user_tracker_stats(user_id)
