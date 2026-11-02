import re
import json
from typing import Dict, Any, Optional
from config import get_gemini_api_key, DEFAULT_GEMINI_MODEL

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

def get_salutation_name(recruiter_email: str, company: str) -> str:
    """Extract human recruiter name from email if possible, else address company team."""
    if not recruiter_email or "@" not in recruiter_email:
        return f"{company} Hiring Team"
        
    local_part = recruiter_email.split("@")[0].lower()
    
    generic = ["recruiting", "recruitment", "talent", "careers", "jobs", "hiring", "people", "hr", "info", "contact"]
    if any(local_part.startswith(g) for g in generic):
        return f"{company} Hiring Team"
        
    parts = re.split(r"[._-]", local_part)
    if parts and parts[0].isalpha() and len(parts[0]) >= 3:
        return parts[0].capitalize()
        
    return f"{company} Recruitment Team"

def resolve_candidate_name(resume_data: Dict[str, Any], user_profile: Optional[Dict[str, Any]] = None) -> tuple[str, bool]:
    """
    Resolve user's first and last name from connected Gmail profile or resume.
    Requirement 6: Retrieve first & last name from Gmail profile.
    If not available, flag needs_confirmation so user can confirm.
    """
    if user_profile:
        full_name = user_profile.get("full_name") or f"{user_profile.get('first_name', '')} {user_profile.get('last_name', '')}".strip()
        if full_name:
            return full_name, False

    resume_name = (resume_data.get("name") or "").strip()
    if resume_name and resume_name.lower() not in ["candidate", "applicant", ""]:
        return resume_name, False

    return "Candidate", True

def generate_natural_email_heuristic(
    resume_data: Dict[str, Any],
    job: Dict[str, Any],
    user_profile: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Produce a concise, natural, human-written cold application email grounded strictly
    in candidate's resume and job requirements.
    Uses Gmail profile name for closing signature.
    """
    candidate_name, needs_confirmation = resolve_candidate_name(resume_data, user_profile)
    candidate_email = (user_profile.get("email") if user_profile and user_profile.get("email") else resume_data.get("email")) or ""
    candidate_phone = resume_data.get("phone") or ""
    years_exp = resume_data.get("years_of_experience", 0)
    original_filename = resume_data.get("original_filename") or resume_data.get("file_name") or "resume"
    
    job_title = job.get("title", "Software Engineer")
    company = job.get("company", "Company")
    recruiter_email = job.get("recruiter_email", "")
    
    salutation_target = get_salutation_name(recruiter_email, company)
    match_info = job.get("match", {})
    matched_skills = match_info.get("matched_skills", [])
    if not matched_skills:
        matched_skills = resume_data.get("skills", [])[:4]
        
    top_skills_str = ", ".join(matched_skills[:3]) if matched_skills else "modern software engineering"
    
    # Extract 1-2 real accomplishments/responsibilities from resume
    work_exps = resume_data.get("work_experience", [])
    highlight_bullets = []
    
    for exp in work_exps:
        resps = exp.get("responsibilities", [])
        for r in resps:
            clean_r = r.strip()
            if len(clean_r) > 25 and len(clean_r) < 140:
                highlight_bullets.append(clean_r)
                if len(highlight_bullets) >= 2:
                    break
        if len(highlight_bullets) >= 2:
            break
            
    if not highlight_bullets:
        highlight_bullets = [
            f"Extensive hands-on background working with {top_skills_str}.",
            f"Delivering reliable, maintainable solutions in fast-paced production environments."
        ]
        
    bullet_text = "\n".join([f"• {b}" for b in highlight_bullets[:2]])
    exp_phrase = f"With {years_exp}+ years of experience" if years_exp > 0 else "With a solid background"

    subject = f"Application: {job_title} - {candidate_name}"
    
    body = f"""Hi {salutation_target},

I am reaching out to express my strong interest in the {job_title} role at {company}. {exp_phrase} working with {top_skills_str}, I believe my background aligns directly with what you are looking for.

A few highlights from my experience that relate to this role:
{bullet_text}

I am particularly excited about {company}'s work and would welcome the opportunity to contribute to your team's goals.

I have attached my resume ({original_filename}) for your review. If you have 10-15 minutes next week, I would love to connect and learn more about your team's priorities.

Thank you for your time and consideration.

Best regards,

{candidate_name}""".strip()

    return {
        "to_email": recruiter_email,
        "subject": subject,
        "body": body,
        "salutation": f"Hi {salutation_target},",
        "candidate_name": candidate_name,
        "needs_name_confirmation": needs_confirmation,
        "original_filename": original_filename
    }

def generate_email_with_gemini(
    resume_data: Dict[str, Any],
    job: Dict[str, Any],
    api_key: str,
    user_profile: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Use Gemini AI to craft an articulate, natural, non-generic email draft.
    """
    if not api_key or not genai:
        return None
        
    client = genai.Client(api_key=api_key)
    
    candidate_name, needs_confirmation = resolve_candidate_name(resume_data, user_profile)
    recruiter_email = job.get("recruiter_email", "")
    company = job.get("company", "Company")
    job_title = job.get("title", "Role")
    salutation_target = get_salutation_name(recruiter_email, company)
    original_filename = resume_data.get("original_filename") or resume_data.get("file_name") or "resume"
    
    prompt = f"""
Write a personalized, professional cold application email from this job seeker to the hiring team.

STRICT GUIDELINES:
1. Tone: Natural, concise, confident, human-written. Do NOT sound like a generic AI template.
2. Avoid clichés: Never say "I hope this email finds you well", "I am thrilled to submit my candidacy", "esteemed organization", or "beacon of innovation".
3. Length: Keep it under 180 words.
4. Facts only: Reference ONLY skills, projects, and experiences that are factually in the resume. Do NOT fabricate metrics.
5. Structure:
   - Subject line: "Application: {job_title} - {candidate_name}"
   - Salutation: "Hi {salutation_target},"
   - Brief introduction stating the role and interest.
   - 2-3 crisp bullet points highlighting actual relevant skills/achievements from the resume.
   - 1 short sentence on why interested in {company}.
   - Explicitly include: "I have attached my resume ({original_filename}) for your review."
   - Polite call to action requesting a brief 15-minute chat.
   - Professional closing signature using ONLY this exact name (do not add email address or phone number):
     Best regards,
     {candidate_name}

CANDIDATE RESUME SUMMARY:
Name: {candidate_name}
Skills: {', '.join(resume_data.get('skills', [])[:10])}
Work History Snippet: {json.dumps(resume_data.get('work_experience', [])[:2])}

TARGET JOB:
Title: {job_title}
Company: {company}
Recruiter Email: {recruiter_email}
Job Description Snippet: {job.get('description', '')[:1000]}
Matched Skills: {', '.join(job.get('match', {}).get('matched_skills', []))}

Return ONLY a JSON object with this exact structure:
{{
  "subject": "Clear subject line",
  "body": "Full email text including salutation, body paragraphs, attachment mention, and sign-off."
}}
Do NOT wrap in markdown code blocks.
"""
    try:
        response = client.models.generate_content(
            model=DEFAULT_GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json"
            )
        )
        parsed = json.loads(response.text)
        return {
            "to_email": recruiter_email,
            "subject": parsed.get("subject", f"Application: {job_title} - {candidate_name}"),
            "body": parsed.get("body", "").strip(),
            "salutation": f"Hi {salutation_target},",
            "candidate_name": candidate_name,
            "needs_name_confirmation": needs_confirmation,
            "original_filename": original_filename
        }
    except Exception as e:
        print(f"Gemini email draft error: {e}")
        return None

def draft_email_for_job(
    resume_data: Dict[str, Any],
    job: Dict[str, Any],
    user_profile: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Main entry point for drafting an email for a job.
    Uses Gemini when key is available; falls back to deterministic natural generator.
    """
    api_key = get_gemini_api_key()
    draft = None
    if api_key:
        draft = generate_email_with_gemini(resume_data, job, api_key, user_profile)
        
    if not draft:
        draft = generate_natural_email_heuristic(resume_data, job, user_profile)
        
    return draft
