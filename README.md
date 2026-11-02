---
title: JobFlow AI
emoji: 💼
colorFrom: emerald
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# JobFlow AI — Intelligent Job Search & Gmail Drafting Agent

An AI-powered job search and personalized email drafting agent built with FastAPI, Python, Google Gemini, and Gmail API.

---

## Key Capabilities & Features

### 1. Multi-Format Resume Analysis (PDF & DOCX)
- Upload your resume in **PDF** (`.pdf`) or **Word** (`.docx`) format.
- Strictly grounded factual extraction: **No invented skills, fake dates, or hallucinated qualifications**.
- Automatically extracts:
  - Technical skills, tools, programming languages, and frameworks.
  - Work history, duration, and calculated total years of experience.
  - Key responsibilities and quantifiable achievements.
  - Education, degrees, universities, and industry certifications.
  - Candidate contact information (email, phone, LinkedIn, GitHub).
- Includes two 1-click pre-built sample resumes for instant testing:
  - `Senior Full Stack Software Engineer` (`.docx`)
  - `AI / Machine Learning Engineer` (`.pdf`)

### 2. Multi-Source Job Search Engine
- Aggregates live postings from public job sources including **Arbeitnow**, **Remotive**, **Jobicy**, and company career portals.
- Collects for every job:
  - Job title and company name.
  - Cleaned job description and required tech stack.
  - Location and remote work status.
  - Direct application portal link.
  - Recruiter / hiring manager email (extracted from description or company domain).
  - Visa sponsorship status (H-1B transfer, sponsorship provided, or citizen/PR required).
  - Posting freshness date.
- Automatic hash deduplication and freshness sorting.

### 3. Factual 4-Dimension Job Matching
Calculates a 0-100% Match Score across:
1. **Skills & Tech Stack Overlap (40%)**: Compares required tools with actual resume skills.
2. **Experience Level & Seniority Fit (25%)**: Evaluates candidate's actual years against required seniority.
3. **Role & Domain Alignment (20%)**: Matches past projects, titles, and responsibilities.
4. **Preferences & Visa Compatibility (15%)**: Ensures visa sponsorship and remote options align.
- Generates transparent, human-readable explanations:
  - **"Why This Job is Relevant"**: 2-3 specific points referencing the candidate's actual background.
  - **"Important Missing Requirements"**: Explicitly lists missing skills or gaps.

### 4. Natural, Human-Sounding Email Drafting
- Generates concise, professional cold emails that sound like a real person, not robotic AI fluff.
- Includes:
  - Tailored subject line (e.g., `Application: Senior Full Stack Engineer - Alex Morgan`).
  - Addressed to named recruiter or company hiring team.
  - 1-2 sentence compelling intro.
  - 2-3 bullet points connecting real resume accomplishments to the role's needs.
  - Why interested in this company.
  - Explicit mention that resume is attached.
  - Professional sign-off with candidate contact details.
- Fully editable inline in the dashboard before saving.

### 5. Gmail Integration with Strict Safety Policy
- Connects directly to your Gmail account via Google OAuth 2.0 (`https://www.googleapis.com/auth/gmail.compose`).
- **Strict Safety Guarantee**:
  - Saves drafts directly into your **Gmail Drafts** folder (`users.drafts.create`).
  - **NEVER sends an email, submits an application, or contacts anyone without your explicit approval**.
- Option to attach the uploaded resume (PDF/DOCX) directly to the Gmail draft.
- Fallback: "Download as .eml" to open directly in Microsoft Outlook, Apple Mail, or Thunderbird, and 1-click clipboard copy.

### 6. Interactive Results Dashboard
Displays the required table:
| Job Title | Company | Location | Match Score | Application Link | Email Draft Status |
|---|---|---|---|---|---|

- Match Score badges (color-coded).
- Filter by keyword, location, remote-only, visa requirement, and minimum score threshold.
- Interactive slide-over modal to inspect full descriptions, match analysis, and edit email drafts.
- Batch action: "Draft Top Matches to Gmail" for all positions above threshold.
- Export results to CSV.

---

## Quickstart Guide

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```
*(Dependencies: `fastapi`, `uvicorn`, `requests`, `beautifulsoup4`, `python-multipart`, `google-auth`, `google-auth-oauthlib`, `google-api-python-client`, `pypdf`, `python-docx`, `reportlab`, `google-genai`)*

### 2. Start the Application
Run the FastAPI server:
```bash
python app.py
```
Or with uvicorn:
```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Open in Browser
Navigate to:
```
http://127.0.0.1:8000
```

---

## Gmail Integration Setup (Optional for Direct Gmail Sync)

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable the **Gmail API**.
3. Go to **APIs & Services > Credentials** > Create Credentials > **OAuth Client ID**.
4. Select Application Type: **Desktop App**.
5. Download the JSON file as `client_secret.json`.
6. In JobFlow AI:
   - Click the **Settings** icon (top right) and upload your `client_secret.json`.
   - Click the **Gmail: Not Connected** button and authorize access in the browser popup.
   - All drafted emails will now appear instantly in your Gmail Drafts folder!

---

## Project Structure
```
Job_Search/
├── app.py                     # FastAPI application & REST endpoints
├── config.py                  # Environment config and paths
├── resume_parser.py           # Multi-format PDF/DOCX parser & factual analyzer
├── job_searcher.py            # Multi-source live job aggregator & deduplicator
├── job_matcher.py             # 4-dimension scoring engine & gap analyzer
├── email_drafter.py           # Human-sounding personalized cold email drafter
├── gmail_service.py           # Gmail OAuth 2.0 & Drafts API integration
├── sample_data/               # Pre-built test resumes (DOCX & PDF)
│   ├── sample_resume_fullstack.docx
│   ├── sample_resume_ai_engineer.pdf
│   └── generate_samples.py
├── static/                    # Frontend UI
│   ├── index.html             # Dashboard markup & modals
│   ├── styles.css             # Tailored dark styling
│   └── app.js                 # Frontend interactions & API bindings
├── requirements.txt           # Python package list
└── README.md                  # Documentation
```
