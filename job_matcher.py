import re
from typing import Dict, Any, List, Tuple
from config import get_gemini_api_key, DEFAULT_GEMINI_MODEL
from job_searcher import extract_experience_requirements

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

def calculate_skills_match(resume_skills: List[str], raw_resume_text: str, required_skills: List[str]) -> Tuple[float, List[str], List[str]]:
    """
    Compare required job skills with resume skills and raw resume text.
    Returns (score_ratio, matched_skills, missing_skills).
    """
    if not required_skills:
        return 1.0, [], []
        
    resume_skills_lower = {s.lower() for s in resume_skills}
    text_lower = raw_resume_text.lower()
    
    matched = []
    missing = []
    
    for req in required_skills:
        req_clean = req.strip()
        req_lower = req_clean.lower()
        
        # Check in parsed skills list
        is_matched = req_lower in resume_skills_lower
        
        # Also check word boundary in raw resume text
        if not is_matched:
            pattern = r"(?:\b|_)" + re.escape(req_lower) + r"(?:\b|_)"
            if re.search(pattern, text_lower):
                is_matched = True
                
        if is_matched:
            matched.append(req_clean)
        else:
            missing.append(req_clean)
            
    match_ratio = len(matched) / len(required_skills) if required_skills else 1.0
    return match_ratio, matched, missing

def calculate_experience_fit(candidate_years: float, job_title: str, job_desc: str) -> float:
    """
    Calculate fit between candidate's years of experience and job seniority.
    Returns score between 0.0 and 1.0.
    """
    # Extract experience requirements using full description, title, and metadata
    exp_meta = extract_experience_requirements(job_desc, job_title)
    if exp_meta.get("is_fresher") or (exp_meta.get("min_years") == 0.0):
        target_years = 0.0
    elif exp_meta.get("min_years") is not None:
        target_years = exp_meta["min_years"]
    elif exp_meta.get("is_senior"):
        target_years = 5.0
    else:
        target_years = 3.0  # unspecified or mid-level default

    if target_years == 0.0:
        return 1.0
    if candidate_years >= target_years:
        return 1.0
    elif candidate_years >= (target_years - 1.5):
        return 0.85
    elif candidate_years >= (target_years - 3.0):
        return 0.65
    else:
        return max(0.3, candidate_years / max(target_years, 1.0))

def calculate_title_domain_overlap(resume_data: Dict[str, Any], job_title: str, job_desc: str) -> float:
    """Check alignment between past roles/projects and the target job domain."""
    score = 0.5  # baseline
    job_lower = f"{job_title} {job_desc}".lower()
    
    # Check if candidate held similar titles
    work_exps = resume_data.get("work_experience", [])
    for exp in work_exps:
        title = exp.get("title") or exp.get("title_and_company") or ""
        title_lower = title.lower()
        
        # Direct word matches
        words = [w for w in title_lower.split() if len(w) > 3]
        for w in words:
            if w in job_lower:
                score += 0.1
                
    # Check project keywords
    projects = resume_data.get("projects", [])
    for p in projects:
        p_name = p.get("name") or p.get("title") or ""
        if any(w.lower() in job_lower for w in p_name.split() if len(w) > 3):
            score += 0.05
            
    return min(1.0, score)

def match_job_with_resume(
    resume_data: Dict[str, Any],
    job: Dict[str, Any],
    preferences: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Compare resume with job description and calculate match score (0-100),
    providing explanation and missing requirements.
    """
    if preferences is None:
        preferences = {}
        
    if resume_data.get("has_resume") is False:
        req_skills = job.get("required_skills", [])
        matched_skills = [s for s in req_skills if any(k.lower() in s.lower() for k in resume_data.get("skills", []))] if resume_data.get("skills") else req_skills[:3]
        missing_skills = [s for s in req_skills if s not in matched_skills][:3]
        
        pref_score = 15.0
        loc_match = True
        target_locations = preferences.get("locations", [])
        if target_locations:
            from job_searcher import is_location_compatible
            loc_match = is_location_compatible(job.get("location", ""), job.get("description", ""), target_locations)
            
        base_score = 75 if loc_match else 55
        if matched_skills:
            base_score = min(92, base_score + len(matched_skills) * 4)

        return {
            "job_id": job.get("id"),
            "match_score": base_score,
            "match_level": "High Match" if base_score >= 80 else "Good Match",
            "match_level_color": "emerald" if base_score >= 80 else "blue",
            "score_breakdown": {
                "skills": 30.0,
                "experience": 20.0,
                "domain": 15.0,
                "preferences": 10.0
            },
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "why_relevant": "Matches your search criteria and target role. Upload your resume to unlock grounded AI scoring, skills comparison, and personalized Gmail drafting.",
            "missing_requirements": "Upload your resume in PDF/DOCX to highlight missing skills or certifications."
        }

    raw_resume_text = resume_data.get("raw_text", "")
    resume_skills = resume_data.get("skills", [])
    candidate_years = float(resume_data.get("years_of_experience", 3.0))
    
    # 1. Skills Match (40 points)
    req_skills = job.get("required_skills", [])
    skills_ratio, matched_skills, missing_skills = calculate_skills_match(resume_skills, raw_resume_text, req_skills)
    skills_score = round(skills_ratio * 40.0, 1)
    
    # 2. Experience Fit (25 points)
    exp_ratio = calculate_experience_fit(candidate_years, job.get("title", ""), job.get("description", ""))
    exp_score = round(exp_ratio * 25.0, 1)
    
    # 3. Role & Responsibilities Alignment (20 points)
    domain_ratio = calculate_title_domain_overlap(resume_data, job.get("title", ""), job.get("description", ""))
    domain_score = round(domain_ratio * 20.0, 1)
    
    # 4. Location, Remote & Visa Preferences (15 points)
    pref_score = 15.0
    visa_req = preferences.get("visa_requirement", "any").lower()
    job_visa = job.get("visa_sponsorship", "")
    
    target_locations = preferences.get("locations", [])
    if not target_locations and preferences.get("location"):
        target_locations = [preferences.get("location")]
        
    from job_searcher import is_location_compatible

    valid_targets = [loc for loc in target_locations if loc and loc.lower() not in ["any", "all", "worldwide", "global"]]
    if valid_targets:
        is_matched_loc = any(is_location_compatible(job.get("location", ""), job.get("description", ""), t) for t in valid_targets)
        if not is_matched_loc:
            pref_score -= 8.0

    if visa_req in ["required", "requires sponsorship", "yes"]:
        if "No Sponsorship" in job_visa:
            pref_score -= 5.0
        elif "Visa Sponsorship Available" in job_visa:
            pref_score += 0.0
        else:
            pref_score -= 2.0  # unconfirmed
            
    if preferences.get("remote_only", False) and not job.get("is_remote", False):
        pref_score -= 4.0
        
    pref_score = max(0.0, min(15.0, pref_score))
    
    total_score = int(round(skills_score + exp_score + domain_score + pref_score))
    total_score = max(5, min(99, total_score))
    
    # Match level label
    if total_score >= 80:
        level = "Strong Match"
        level_color = "emerald"
    elif total_score >= 65:
        level = "Good Match"
        level_color = "blue"
    elif total_score >= 50:
        level = "Moderate Match"
        level_color = "amber"
    else:
        level = "Low Match"
        level_color = "rose"

    # Construct concise, factual explanations based on actual resume data
    why_points = []
    if matched_skills:
        top_matched = ", ".join(matched_skills[:4])
        why_points.append(f"Strong tech stack overlap: matches your proven experience with {top_matched}.")
    if candidate_years > 0:
        why_points.append(f"Experience alignment: your {candidate_years} years of background matches the role seniority level.")
    if valid_targets:
        matched_loc_names = [t for t in valid_targets if is_location_compatible(job.get("location", ""), job.get("description", ""), t)]
        if matched_loc_names:
            why_points.append(f"Location match: Role aligns with your preference ({', '.join(matched_loc_names)}).")
    elif job.get("is_remote"):
        why_points.append("Offers remote work flexibility matching your preferences.")
    if "Visa Sponsorship Available" in job_visa:
        why_points.append("Explicitly offers visa sponsorship support.")
        
    why_relevant = " ".join(why_points) if why_points else "Relevant role based on matching engineering experience."
    
    # Missing requirements
    missing_points = []
    if missing_skills:
        top_missing = ", ".join(missing_skills[:3])
        missing_points.append(f"Key technologies not explicitly highlighted in resume: {top_missing}.")
    if "No Sponsorship" in job_visa and visa_req in ["required", "requires sponsorship"]:
        missing_points.append("Job states no visa sponsorship is offered for this opening.")
        
    missing_requirements = " ".join(missing_points) if missing_points else "No major missing requirements detected."
    
    return {
        "job_id": job.get("id"),
        "match_score": total_score,
        "match_level": level,
        "match_level_color": level_color,
        "score_breakdown": {
            "skills": skills_score,
            "experience": exp_score,
            "domain": domain_score,
            "preferences": pref_score
        },
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "why_relevant": why_relevant,
        "missing_requirements": missing_requirements
    }

def rank_and_score_jobs(
    resume_data: Dict[str, Any],
    jobs: List[Dict[str, Any]],
    preferences: Optional[Dict[str, Any]] = None,
    min_score: int = 0
) -> List[Dict[str, Any]]:
    """
    Score all jobs against the resume, attach match details,
    filter by min_score, and sort by match_score descending.
    """
    scored_jobs = []
    for job in jobs:
        match_info = match_job_with_resume(resume_data, job, preferences)
        combined = {**job, "match": match_info}
        if match_info["match_score"] >= min_score:
            scored_jobs.append(combined)
            
    # Sort by match score descending
    scored_jobs.sort(key=lambda x: x["match"]["match_score"], reverse=True)
    return scored_jobs
