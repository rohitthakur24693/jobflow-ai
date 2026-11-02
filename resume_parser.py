import re
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import pypdf
import docx

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

from config import get_gemini_api_key, DEFAULT_GEMINI_MODEL

COMMON_TECH_SKILLS = [
    # BI, Visualization & Analytics Tools
    "Tableau", "Tableau Desktop", "Tableau Server", "Tableau Prep",
    "Alteryx", "Alteryx Designer", "Alteryx Server",
    "Power BI", "PowerBI", "Power Query", "DAX", "Power Pivot",
    "Looker", "Looker Studio", "Google Data Studio",
    "Qlik", "QlikView", "Qlik Sense",
    "Metabase", "Superset", "Cognos", "MicroStrategy", "Spotfire", "Sisense", "QuickSight",
    "Excel", "Advanced Excel", "VBA", "Macros",
    "SAS", "SPSS", "Stata",

    # Data Warehousing & Cloud Databases
    "Snowflake", "BigQuery", "Redshift", "Databricks", "Delta Lake",
    "Synapse", "Azure Synapse", "Teradata",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "SQLite", "DynamoDB", "Cassandra", "Elasticsearch",
    "Oracle", "SQL Server", "T-SQL", "PL/SQL", "ClickHouse", "DuckDB", "Hive", "Presto", "Trino",
    "Firebase", "Supabase", "Neo4j",

    # ETL, Data Engineering & Pipelines
    "dbt", "Airflow", "Apache Airflow", "Apache Spark", "Spark", "PySpark", "Kafka", "Apache Kafka",
    "Informatica", "Talend", "SSIS", "SSRS", "SSAS", "DataStage",
    "Fivetran", "Airbyte", "AWS Glue", "Azure Data Factory", "ADF", "NiFi",
    "Data Modeling", "Data Warehousing", "ETL", "ELT", "Data Pipelines",
    "Business Intelligence", "Data Analysis", "Data Analytics", "Data Visualization",

    # Programming & Scripting Languages
    "Python", "SQL", "R", "Scala", "Julia", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Rust",
    "Ruby", "PHP", "Swift", "Kotlin", "HTML", "CSS", "Bash", "Shell", "PowerShell", "Dart",

    # Frameworks & Libraries
    "React", "React Native", "Next.js", "Vue.js", "Nuxt.js", "Angular", "Node.js", "Express",
    "FastAPI", "Django", "Flask", "Spring Boot", "ASP.NET", ".NET", "Ruby on Rails", "Laravel",
    "Tailwind CSS", "Bootstrap", "Redux", "GraphQL", "REST APIs", "gRPC", "WebSocket",

    # AI, ML & Data Science
    "Machine Learning", "Deep Learning", "Artificial Intelligence", "Data Science",
    "PyTorch", "TensorFlow", "Keras", "Scikit-Learn", "Pandas", "NumPy", "SciPy", "Statsmodels",
    "OpenCV", "HuggingFace", "LangChain", "LlamaIndex", "LLM", "NLP", "Natural Language Processing",
    "Computer Vision", "Generative AI", "RAG", "Transformers",
    "Predictive Modeling", "A/B Testing", "Hypothesis Testing", "Statistics",

    # Cloud & DevOps
    "AWS", "Amazon Web Services", "Azure", "Microsoft Azure", "Google Cloud", "GCP",
    "Docker", "Kubernetes", "Terraform", "Ansible", "CI/CD", "GitHub Actions", "GitLab CI", "Jenkins", "Helm",
    "CloudFormation", "Linux", "Nginx", "Serverless", "Lambda",

    # Tools & Methodologies
    "Git", "GitHub", "GitLab", "Jira", "Agile", "Scrum", "Microservices", "TDD", "Unit Testing",
    "System Design", "Distributed Systems", "API Design", "Performance Optimization"
]

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text cleanly from PDF file using pypdf."""
    text_content = []
    try:
        reader = pypdf.PdfReader(pdf_path)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_content.append(text)
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
    return "\n".join(text_content).strip()

def extract_text_from_docx(docx_path: str) -> str:
    """Extract text cleanly from Word DOCX file including tables."""
    text_content = []
    try:
        doc = docx.Document(docx_path)
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_content.append(paragraph.text.strip())
        for table in doc.tables:
            for row in table.rows:
                row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_text:
                    text_content.append(" | ".join(row_text))
    except Exception as e:
        print(f"Error reading DOCX {docx_path}: {e}")
    return "\n".join(text_content).strip()

def extract_text_from_file(file_path: str) -> str:
    """Extract text based on file extension."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in [".docx", ".doc"]:
        return extract_text_from_docx(file_path)
    elif ext in [".txt", ".md"]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    else:
        raise ValueError(f"Unsupported resume file format: {ext}. Please provide PDF or DOCX.")

def heuristic_parse_resume(raw_text: str) -> Dict[str, Any]:
    """
    Robust rule-based parser that strictly extracts facts without hallucinating.
    """
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    
    # 1. Contact Info
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", raw_text)
    email = email_match.group(0) if email_match else ""
    
    phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", raw_text)
    phone = phone_match.group(0) if phone_match else ""
    
    linkedin_match = re.search(r"(https?://)?(www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+", raw_text)
    linkedin = linkedin_match.group(0) if linkedin_match else ""
    
    github_match = re.search(r"(https?://)?(www\.)?github\.com/[a-zA-Z0-9_-]+", raw_text)
    github = github_match.group(0) if github_match else ""
    
    # Name: First substantial line without email/phone/url
    name = "Candidate"
    for line in lines[:5]:
        if not re.search(r"(@|http|www|github|linkedin|\+?\d{3})", line, re.IGNORECASE) and len(line) < 40:
            name = line
            break
            
    # 2. Extract Skills
    found_skills = []
    text_lower = raw_text.lower()
    
    # Pass A: Whole-Resume Direct Vocabulary Scan
    # If a skill exists anywhere in resume (Tableau, Alteryx, Power BI, Python, etc.)
    for skill in COMMON_TECH_SKILLS:
        # Match as whole word/phrase
        pattern = r"(?:\b|_)" + re.escape(skill.lower()) + r"(?:\b|_)"
        if re.search(pattern, text_lower):
            if skill not in found_skills:
                found_skills.append(skill)
                
    # Pass B: Resilient Skills Section Extraction
    # Matches: Skills, Technical Skills, Core Competencies, Tools & Technologies, Key Skills, Proficiencies, etc.
    skills_header_pattern = r"(?i)(?:^|\n)\s*(?:Technical\s+|Core\s+|Key\s+|Professional\s+)?(?:Skills|Competencies|Proficiencies|Tools|Technologies|Tech\s+Stack)(?:\s*(?:&|and|\/)\s*(?:Tools|Technologies|Platforms|Frameworks|Proficiencies|Competencies))?\s*[:\n\-–—]"
    skills_headers = list(re.finditer(skills_header_pattern, raw_text))
    
    for match in skills_headers:
        start_idx = match.end()
        # Find next major header (Experience, Education, Projects, Certifications)
        next_header = re.search(r"(?i)\n\s*(?:Work\s+Experience|Experience|Employment|Education|Projects|Certifications|Summary|Objective)\s*[:\n\-–—]", raw_text[start_idx:])
        end_idx = start_idx + (next_header.start() if next_header else 800)
        skills_section = raw_text[start_idx:end_idx]
        
        # Split tokens by comma, semicolon, bullet, vertical pipe, slash, or newline
        raw_tokens = re.split(r"[,;|\n•\*\·\t]", skills_section)
        for token in raw_tokens:
            token_clean = token.strip()
            # Strip category prefixes e.g. "BI Tools: Tableau" or "Languages - Python"
            token_clean = re.sub(r"^[^:\-–—]+[:\-–—]\s*", "", token_clean).strip()
            
            # If token contains slash like "Tableau / Alteryx", split it
            sub_tokens = [t.strip() for t in token_clean.split("/") if t.strip()] if "/" in token_clean and len(token_clean) < 40 else [token_clean]
            
            for sub_token in sub_tokens:
                if sub_token and len(sub_token) < 35:
                    if not re.search(r"(?i)(years|level|proficient|experience|advanced|intermediate|beginner|familiar|knowledge|skills)", sub_token):
                        # Canonical formatting
                        clean_item = sub_token.strip("()[]{}., ")
                        if len(clean_item) >= 2:
                            # Avoid duplicates (case-insensitive check)
                            if not any(clean_item.lower() == s.lower() for s in found_skills):
                                found_skills.append(clean_item)
                    
    # 3. Work Experience & Years
    experience_list = []
    exp_header = re.search(r"(?i)\n(?:Work\s+|Professional\s+)?Experience\s*[:\n]", raw_text)
    years_detected = 0.0
    
    # Priority A: Check explicit statement in summary/text like "6+ years of experience" or "4+ years experience"
    exp_text_match = re.search(r"(\d+(?:\.\d+)?)\+?\s*years?(?:\s+of)?\s+(?:professional\s+)?experience", raw_text, re.IGNORECASE)
    if exp_text_match:
        try:
            years_detected = float(exp_text_match.group(1))
        except ValueError:
            pass

    # Priority B: Calculate from the Experience section dates
    if years_detected == 0.0:
        exp_chunk = raw_text
        if exp_header:
            start_idx = exp_header.end()
            next_header = re.search(r"(?i)\n(?:Education|Projects|Certifications|Skills)\s*[:\n]", raw_text[start_idx:])
            end_idx = start_idx + (next_header.start() if next_header else 2500)
            exp_chunk = raw_text[start_idx:end_idx]
            
        import datetime
        current_year = datetime.datetime.now().year
        year_ranges = re.findall(r"\b(20\d\d|19\d\d)\s*(?:-|to|–)\s*(20\d\d|Present|Current)\b", exp_chunk, re.IGNORECASE)
        total_months = 0
        for start_yr, end_yr in year_ranges:
            s = int(start_yr)
            e = current_year if end_yr.lower() in ["present", "current"] else int(end_yr)
            if e >= s:
                total_months += (e - s) * 12
        if total_months > 0:
            years_detected = round(total_months / 12.0, 1)

    # Extract roles/companies heuristically
    if exp_header:
        start_idx = exp_header.end()
        next_header = re.search(r"(?i)\n(?:Education|Projects|Certifications|Skills)\s*[:\n]", raw_text[start_idx:])
        end_idx = start_idx + (next_header.start() if next_header else 2000)
        exp_text = raw_text[start_idx:end_idx]
        exp_lines = [l.strip() for l in exp_text.splitlines() if l.strip()]
        
        current_job = None
        for line in exp_lines:
            is_date_line = re.search(r"\b(20\d\d|19\d\d|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", line)
            is_bullet = line.startswith(("-", "•", "*", "·"))
            
            if is_date_line and not is_bullet:
                if current_job:
                    experience_list.append(current_job)
                current_job = {
                    "title_and_company": line,
                    "responsibilities": []
                }
            elif is_bullet:
                if current_job:
                    current_job["responsibilities"].append(line.lstrip("-•*· ").strip())
                else:
                    current_job = {"title_and_company": "Role / Experience", "responsibilities": [line.lstrip("-•*· ").strip()]}
            elif current_job and len(current_job["responsibilities"]) < 10:
                current_job["responsibilities"].append(line)
        if current_job:
            experience_list.append(current_job)

    # 4. Education
    education_list = []
    edu_matches = re.findall(r"(?i)\b(Bachelor(?:'s)?|Master(?:'s)?|B\.S\.|M\.S\.|B\.Tech|M\.Tech|Ph\.D\.|Associate|Degree)[^,\n.]*(?:in\s+[^,\n.]+)?", raw_text)
    for edu in edu_matches:
        edu_str = edu.strip()
        if edu_str and edu_str not in education_list:
            education_list.append(edu_str)
            
    # 5. Certifications
    certs = []
    cert_matches = re.findall(r"(?i)\b(AWS\s+Certified[^\n,]*|Google\s+Cloud\s+Certified[^\n,]*|Azure\s+Certified[^\n,]*|Tableau\s+Desktop\s+Specialist[^\n,]*|Tableau\s+Certified[^\n,]*|Alteryx\s+Designer\s+Core[^\n,]*|Alteryx\s+Certified[^\n,]*|CKA|CKAD|PMP|Certified\s+Scrum\s+Master[^\n,]*|CISSP)", raw_text)
    for cert in cert_matches:
        if cert.strip() and cert.strip() not in certs:
            certs.append(cert.strip())

    # 6. Projects
    projects = []
    proj_header = re.search(r"(?i)\nProjects\s*[:\n]", raw_text)
    if proj_header:
        start_idx = proj_header.end()
        next_header = re.search(r"(?i)\n(?:Education|Certifications|Skills|Experience)\s*[:\n]", raw_text[start_idx:])
        end_idx = start_idx + (next_header.start() if next_header else 1000)
        proj_text = raw_text[start_idx:end_idx]
        p_lines = [l.strip() for l in proj_text.splitlines() if l.strip()]
        curr_proj = None
        for line in p_lines:
            if not line.startswith(("-", "•", "*", "·")) and len(line) < 60:
                if curr_proj:
                    projects.append(curr_proj)
                curr_proj = {"title": line, "details": []}
            elif curr_proj:
                curr_proj["details"].append(line.lstrip("-•*· ").strip())
        if curr_proj:
            projects.append(curr_proj)

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "location": "",
        "links": {"linkedin": linkedin, "github": github},
        "skills": found_skills,
        "years_of_experience": years_detected,
        "work_experience": experience_list,
        "education": education_list,
        "certifications": certs,
        "projects": projects,
        "raw_text": raw_text
    }

def analyze_resume_with_gemini(raw_text: str, api_key: str) -> Optional[Dict[str, Any]]:
    """
    Extract structured resume data using Gemini AI with strict grounding rules:
    'Do not invent skills, qualifications, or achievements.'
    """
    if not api_key or not genai:
        return None
        
    client = genai.Client(api_key=api_key)
    prompt = f"""
You are a precise, factual resume analyzer.
Strict rule: Extract ONLY facts that are explicitly mentioned in the resume below.
DO NOT invent, hallucinate, assume, or extrapolate skills, technologies, qualifications, dates, or achievements.
Be sure to capture all tools, BI software, databases, and technologies mentioned (such as Tableau, Alteryx, Power BI, SQL, Python, Excel, etc.).
If a section or field is not mentioned, leave it empty.

Resume Content:
\"\"\"
{raw_text[:12000]}
\"\"\"

Return a valid JSON object strictly matching this schema:
{{
  "name": "Candidate's full name",
  "email": "Email address or empty string",
  "phone": "Phone number or empty string",
  "location": "City, State or Country if stated",
  "summary": "1-2 sentence factual summary of experience from resume",
  "skills": ["List of explicitly stated skills, tools, programming languages, technologies, and BI platforms"],
  "years_of_experience": 0.0,
  "work_experience": [
    {{
      "title": "Job Title",
      "company": "Company Name",
      "dates": "Start - End Date",
      "responsibilities": ["Explicit responsibilities/achievements"]
    }}
  ],
  "education": [
    {{
      "degree": "Degree name",
      "institution": "University/College",
      "year": "Graduation year if stated"
    }}
  ],
  "certifications": ["Certifications explicitly listed"],
  "projects": [
    {{
      "name": "Project name",
      "technologies": ["Technologies mentioned in project"],
      "description": "Brief description"
    }}
  ]
}}
Respond ONLY with the JSON object, without markdown formatting or code fences.
"""
    try:
        response = client.models.generate_content(
            model=DEFAULT_GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
        )
        parsed = json.loads(response.text)
        parsed["raw_text"] = raw_text
        return parsed
    except Exception as e:
        print(f"Gemini resume analysis error: {e}")
        return None

def parse_resume(file_path: str) -> Dict[str, Any]:
    """
    Main entry point: Extracts text from PDF/DOCX and performs structured analysis.
    Uses Gemini when key is available, falls back to deterministic heuristic parser.
    """
    raw_text = extract_text_from_file(file_path)
    if not raw_text.strip():
        raise ValueError("Could not extract any text from the provided resume file. Please ensure the file is not empty or password protected.")

    api_key = get_gemini_api_key()
    parsed_data = None
    if api_key:
        parsed_data = analyze_resume_with_gemini(raw_text, api_key)
        
    if not parsed_data:
        parsed_data = heuristic_parse_resume(raw_text)

    # Attach file info
    parsed_data["file_path"] = str(file_path)
    parsed_data["file_name"] = Path(file_path).name
    return parsed_data
