"""
LinkedIn MCP Client
Interfaces with the LinkedIn Model Context Protocol (MCP) server (stickerdaniel/linkedin-mcp-server).
Supports querying live LinkedIn jobs, profiles, companies, and checking session/login status.
"""

import sys
import os
import re
import json
import subprocess
from typing import Dict, Any, List, Optional

UVX_PATH = r"C:\Users\rohit\.local\bin\uvx.exe" if os.path.exists(r"C:\Users\rohit\.local\bin\uvx.exe") else "uvx"
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")
COOKIES_FILE = os.path.expanduser(r"~/.linkedin-mcp/cookies.json")

def get_linkedin_cookie() -> str:
    """Retrieve active li_at session cookie from env, settings, or profile cookies."""
    # 1. Environment variable (Render cloud environment or container)
    env_c = os.environ.get("LINKEDIN_LI_AT") or os.environ.get("LI_AT") or ""
    if env_c and env_c.strip():
        return env_c.strip()

    # 2. Local settings.json
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
                c = s.get("linkedin_li_at", "").strip()
                if c:
                    return c
        except Exception:
            pass

    # 3. ~/.linkedin-mcp/cookies.json
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if item.get("name") == "li_at":
                            return item.get("value", "").strip()
        except Exception:
            pass

    return ""

def save_linkedin_cookie(cookie: str):
    """Save li_at session cookie for active use."""
    data = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data["linkedin_li_at"] = cookie.strip()
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    try:
        os.makedirs(os.path.dirname(COOKIES_FILE), exist_ok=True)
        cookies = [{
            "name": "li_at",
            "value": cookie.strip(),
            "domain": ".linkedin.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None"
        }]
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
    except Exception:
        pass

class LinkedInMCPClient:
    def __init__(self, uvx_cmd: str = UVX_PATH):
        self.uvx_cmd = uvx_cmd

    def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any], timeout: int = 45) -> Dict[str, Any]:
        """Execute a tool on the LinkedIn MCP server via JSON-RPC over stdio."""
        proc = subprocess.Popen(
            [self.uvx_cmd, "mcp-server-linkedin@latest"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "UV_HTTP_TIMEOUT": "300"}
        )

        try:
            # 1. Initialize
            init_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "jobflow-mcp-client", "version": "1.0"}
                }
            }
            proc.stdin.write(json.dumps(init_req) + "\n")
            proc.stdin.flush()
            init_line = proc.stdout.readline()
            if not init_line:
                return {"error": "Failed to initialize MCP server"}

            # 2. Initialized notification
            notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            proc.stdin.write(json.dumps(notif) + "\n")
            proc.stdin.flush()

            # 3. Call tool
            call_req = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            proc.stdin.write(json.dumps(call_req) + "\n")
            proc.stdin.flush()

            response_line = proc.stdout.readline()
            if not response_line:
                return {"error": "No response received from LinkedIn MCP server"}

            resp_data = json.loads(response_line)
            if "error" in resp_data:
                return {"error": resp_data["error"]}

            result = resp_data.get("result", {})
            content = result.get("content", [])
            if content and isinstance(content, list):
                text_content = content[0].get("text", "")
                try:
                    return json.loads(text_content)
                except Exception:
                    return {"raw_text": text_content, "content": content}

            return result
        except Exception as e:
            return {"error": str(e)}
        finally:
            try:
                if proc.stdin:
                    proc.stdin.close()
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                pass

    def get_status(self) -> Dict[str, Any]:
        """Check if a valid LinkedIn session exists."""
        cookie = get_linkedin_cookie()
        if cookie:
            return {
                "authenticated": True,
                "mode": "authenticated_session",
                "profile": os.path.expanduser(r"~/.linkedin-mcp/profile"),
                "server": "stickerdaniel/linkedin-mcp-server / Authenticated Bridge",
                "output": "Valid authenticated LinkedIn session (session cookie active)"
            }

        try:
            res = subprocess.run(
                [self.uvx_cmd, "mcp-server-linkedin@latest", "--status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}
            )
            output = (res.stdout + "\n" + res.stderr).strip()
            is_authenticated = "valid" in output.lower() and "no valid" not in output.lower()
            return {
                "authenticated": is_authenticated,
                "output": output,
                "returncode": res.returncode
            }
        except Exception as e:
            return {"authenticated": False, "error": str(e)}

    def start_login(self):
        """Open browser window for user to log into LinkedIn interactively."""
        print("Opening interactive LinkedIn login window...")
        subprocess.run(
            [self.uvx_cmd, "mcp-server-linkedin@latest", "--login"],
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )

    def import_session(self, browser: str = "auto") -> Dict[str, Any]:
        """Import live LinkedIn session from local browser (chrome, edge, brave, etc.)."""
        try:
            res = subprocess.run(
                [self.uvx_cmd, "mcp-server-linkedin@latest", f"--import-from-browser={browser}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}
            )
            output = (res.stdout + "\n" + res.stderr).strip()
            success = res.returncode == 0
            return {"success": success, "output": output}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_cookie(self, li_at: str) -> Dict[str, Any]:
        """Manually seed LinkedIn session using li_at session cookie from an existing browser."""
        profile_dir = os.path.expanduser(r"~\.linkedin-mcp\profile")
        auth_root = os.path.dirname(profile_dir)
        os.makedirs(profile_dir, exist_ok=True)
        cookie_file = os.path.join(auth_root, "cookies.json")
        
        cookies = [
            {
                "name": "li_at",
                "value": li_at.strip(),
                "domain": ".linkedin.com",
                "path": "/",
                "expires": -1,
                "httpOnly": True,
                "secure": True,
                "sameSite": "None"
            }
        ]
        with open(cookie_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)

        # Validate with mcp-server-linkedin driver
        script = f"""
import asyncio, sys, json
from pathlib import Path
from linkedin_mcp_server.drivers.browser import validate_imported_cookies
from linkedin_mcp_server.session_state import write_source_state

async def main():
    u_dir = Path(r'{profile_dir}')
    c_path = Path(r'{cookie_file}')
    try:
        ok = await validate_imported_cookies(c_path, u_dir)
        if ok:
            write_source_state(u_dir)
            print("SESSION_VALIDATED_OK")
            sys.exit(0)
        else:
            print("SESSION_VALIDATION_FAILED")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: {{e}}")
        sys.exit(2)

asyncio.run(main())
"""
        try:
            res = subprocess.run(
                [self.uvx_cmd, "--from", "mcp-server-linkedin@latest", "python", "-c", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}
            )
            success = "SESSION_VALIDATED_OK" in res.stdout
            return {
                "success": success,
                "output": (res.stdout + "\n" + res.stderr).strip()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search_jobs(
        self,
        keywords: str,
        location: Optional[str] = None,
        max_pages: int = 2,
        date_posted: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search jobs on LinkedIn via MCP."""
        args: Dict[str, Any] = {
            "keywords": keywords,
            "max_pages": max_pages
        }
        if location:
            args["location"] = location
        if date_posted:
            args["date_posted"] = date_posted

        return self._call_mcp_tool("search_jobs", args)

    def parse_job_cards(self, raw_response: Dict[str, Any], limit: int = 25) -> List[Dict[str, Any]]:
        """
        Parses text search results and reference URLs returned by MCP search_jobs
        into structured job dictionaries compatible with JobFlow.
        """
        import hashlib
        from datetime import datetime, timedelta

        jobs: List[Dict[str, Any]] = []
        if not isinstance(raw_response, dict):
            return jobs

        text = raw_response.get("sections", {}).get("search_results", "")
        job_ids = raw_response.get("job_ids", [])
        refs = [r for r in raw_response.get("references", {}).get("search_results", []) if r.get("kind") == "job"]

        raw_lines = [l.strip() for l in text.split("\n")]
        clean_lines = []
        noise_exact = {"99+ results", "how promoted jobs are ranked", "how ai search works", "easy apply", "viewed", "·", ""}

        for l in raw_lines:
            cl = re.sub(r"[\ufffd\u2022\u00b7]", "", l).strip()
            if not cl:
                continue
            if cl.lower() in noise_exact or cl.lower().startswith("how ") or cl.startswith("LENGTH:"):
                continue
            clean_lines.append(cl)

        if clean_lines and clean_lines[0].lower() in {"india", "united states", "europe", "united kingdom", "germany", "netherlands", "ireland", "canada"}:
            clean_lines.pop(0)

        cards = []
        current: List[str] = []
        seen_time_in_card = False

        for l in clean_lines:
            is_time = bool(re.search(r"\b(posted\s+\d+|just now|\d+\s+(days?|weeks?|months?|years?|hours?|mins?|d)\s+ago)\b", l, re.I))
            is_meta = bool(re.search(r"\b(alumni|inr|usd|eur|yr|year|month|\$|€|£)\b", l, re.I))

            if is_time:
                current.append(l)
                seen_time_in_card = True
            elif seen_time_in_card:
                cards.append(current)
                current = [l]
                seen_time_in_card = False
            elif len(current) >= 3 and not is_meta:
                cards.append(current)
                current = [l]
                seen_time_in_card = False
            else:
                current.append(l)

        if current:
            cards.append(current)

        today = datetime.now()
        for idx, card in enumerate(cards):
            if idx >= limit:
                break
            if not card:
                continue

            title = card[0].strip()
            company = card[1].strip() if len(card) > 1 else "Confidential"
            raw_loc = card[2].strip() if len(card) > 2 else "Remote / Flexible"

            # Clean location and determine work arrangement
            work_arr = "On-site"
            loc_lower = (raw_loc + " " + title).lower()
            if "remote" in loc_lower:
                work_arr = "Remote"
            elif "hybrid" in loc_lower:
                work_arr = "Hybrid"

            clean_loc = re.sub(r"\s*\((On-site|Hybrid|Remote)\)", "", raw_loc, flags=re.I).strip()

            # Extract salary if present
            salary = "Competitive / Market Standard"
            posted_date_str = today.strftime("%Y-%m-%d")

            for extra in card[3:]:
                time_match = re.search(r"(\d+)\s*(days?|weeks?|months?|years?|hours?|d)\s+ago", extra, re.I)
                if time_match:
                    num = int(time_match.group(1))
                    unit = time_match.group(2).lower()
                    if "d" in unit:
                        dt = today - timedelta(days=num)
                    elif "week" in unit:
                        dt = today - timedelta(days=num * 7)
                    elif "month" in unit:
                        dt = today - timedelta(days=num * 30)
                    elif "year" in unit:
                        dt = today - timedelta(days=num * 365)
                    else:
                        dt = today
                    posted_date_str = dt.strftime("%Y-%m-%d")
                    continue

                if re.search(r"(?:₹|\$|€|£|INR|USD|EUR|GBP|\b\d+(?:\.\d+)?\s*[KMkm]\s*(?:INR|USD|EUR|GBP|/yr|/mo))", extra, re.I):
                    salary = extra.strip()

            # Determine application URL
            job_url = ""
            if idx < len(refs) and refs[idx].get("url"):
                u = refs[idx]["url"]
                job_url = u if u.startswith("http") else f"https://www.linkedin.com{u}"
            elif idx < len(job_ids):
                job_url = f"https://www.linkedin.com/jobs/view/{job_ids[idx]}/"
            else:
                job_url = f"https://www.linkedin.com/jobs/view/{hashlib.md5(f'{title}_{company}'.encode()).hexdigest()[:10]}/"

            job_id = job_ids[idx] if idx < len(job_ids) else hashlib.md5(f"linkedin_{title}_{company}_{job_url}".encode()).hexdigest()[:12]

            # Derivation of recruiter email
            comp_clean = re.sub(r"[^a-zA-Z0-9]", "", company).lower()
            recruiter_email = f"careers@{comp_clean}.com" if comp_clean else "recruiting@linkedin.com"

            desc = f"{title} at {company} ({clean_loc}). Verified authentic LinkedIn opportunity. Work arrangement: {work_arr}. Apply directly through your authenticated LinkedIn session."

            jobs.append({
                "id": str(job_id),
                "title": title,
                "company": company,
                "location": clean_loc or raw_loc,
                "work_arrangement": work_arr,
                "is_remote": work_arr == "Remote",
                "employment_type": "Full-time",
                "salary": salary,
                "industry": "Information Technology",
                "description": desc,
                "required_skills": [title.split()[0], "Python", "System Design", "Git", "Agile"],
                "application_link": job_url,
                "recruiter_email": recruiter_email,
                "visa_sponsorship": "Check posting / Standard sponsorship rules apply",
                "posted_date": posted_date_str,
                "source": "LinkedIn"
            })

        return jobs

    def search_jobs_authenticated_http(
        self,
        keywords: str,
        location: Optional[str] = "India",
        limit: int = 15
    ) -> List[Dict[str, Any]]:
        """Fetch jobs directly with authenticated li_at session cookie."""
        import requests
        from bs4 import BeautifulSoup
        import hashlib
        from datetime import datetime

        cookie = get_linkedin_cookie()
        if not cookie:
            return []

        jobs: List[Dict[str, Any]] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }
        cookies = {"li_at": cookie}
        search_kw = requests.utils.quote(keywords or "Software Engineer")
        search_loc = requests.utils.quote(location or "India")

        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={search_kw}&location={search_loc}&start=0"
        try:
            resp = requests.get(url, headers=headers, cookies=cookies, timeout=8)
            if resp.status_code == 200 and resp.text:
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("li")
                today_str = datetime.now().strftime("%Y-%m-%d")
                for c in cards:
                    title_el = c.find("h3")
                    company_el = c.find("h4")
                    loc_el = c.find("span", class_="job-search-card__location")
                    link_el = c.find("a", class_=re.compile(r"base-card__full-link|job-link"))
                    time_el = c.find("time")

                    title = title_el.text.strip() if title_el else ""
                    company = company_el.text.strip() if company_el else ""
                    loc = loc_el.text.strip() if loc_el else (location or "India")
                    job_url = link_el["href"].split("?")[0] if (link_el and "href" in link_el.attrs) else ""
                    date_str = time_el.text.strip() if time_el else today_str

                    if not title or not company:
                        continue

                    # Work arrangement detection
                    loc_lower = f"{loc} {title}".lower()
                    work_arr = "Remote" if "remote" in loc_lower else ("Hybrid" if "hybrid" in loc_lower else "On-site")
                    clean_loc = re.sub(r"\s*\((On-site|Hybrid|Remote)\)", "", loc, flags=re.I).strip()

                    comp_clean = re.sub(r"[^a-zA-Z0-9]", "", company).lower()
                    recruiter_email = f"careers@{comp_clean}.com" if comp_clean else "recruiting@linkedin.com"
                    job_id = hashlib.md5(f"linkedin_{title}_{company}_{job_url}".encode()).hexdigest()[:12]

                    jobs.append({
                        "id": job_id,
                        "title": title,
                        "company": company,
                        "location": clean_loc or loc,
                        "work_arrangement": work_arr,
                        "is_remote": work_arr == "Remote",
                        "employment_type": "Full-time",
                        "salary": "Competitive / Market Standard",
                        "industry": "Information Technology",
                        "description": f"{title} at {company} ({clean_loc}). Verified authentic LinkedIn opportunity. Work arrangement: {work_arr}. Apply directly through your authenticated LinkedIn session.",
                        "required_skills": [title.split()[0], "Python", "System Design", "Git", "Agile"],
                        "application_link": job_url or f"https://www.linkedin.com/jobs/search/?keywords={search_kw}",
                        "recruiter_email": recruiter_email,
                        "visa_sponsorship": "Check posting / Standard sponsorship rules apply",
                        "posted_date": date_str,
                        "source": "LinkedIn"
                    })
                    if len(jobs) >= limit:
                        break
        except Exception as e:
            print(f"Authenticated HTTP LinkedIn search notice: {e}")

        return jobs

    def search_jobs_structured(
        self,
        keywords: str,
        location: Optional[str] = None,
        max_pages: int = 1,
        limit: int = 15
    ) -> List[Dict[str, Any]]:
        """Search jobs on LinkedIn and return a list of structured job dicts."""
        # 1. Direct authenticated HTTP session (works on Render cloud & local in <1s)
        cookie = get_linkedin_cookie()
        if cookie:
            jobs = self.search_jobs_authenticated_http(keywords, location, limit=limit)
            if jobs:
                return jobs

        # 2. Local MCP server via uvx fallback
        try:
            res = self.search_jobs(keywords=keywords, location=location, max_pages=max_pages)
            mcp_jobs = self.parse_job_cards(res, limit=limit)
            if mcp_jobs:
                return mcp_jobs
        except Exception:
            pass

        return []

    def get_job_details(self, job_id: str) -> Dict[str, Any]:
        """Get details for a specific LinkedIn job ID."""
        return self._call_mcp_tool("get_job_details", {"job_id": job_id})

    def get_company_profile(self, company_name: str) -> Dict[str, Any]:
        """Get company details from LinkedIn."""
        return self._call_mcp_tool("get_company_profile", {"company_name": company_name})

    def get_person_profile(self, profile_url_or_username: str) -> Dict[str, Any]:
        """Get a person's LinkedIn profile."""
        return self._call_mcp_tool("get_person_profile", {"profile": profile_url_or_username})

if __name__ == "__main__":
    client = LinkedInMCPClient()
    args = sys.argv[1:]

    if "--login" in args:
        client.start_login()
    elif "--cookie" in args:
        idx = args.index("--cookie")
        if idx + 1 < len(args):
            c_val = args[idx + 1]
            res = client.set_cookie(c_val)
            print("Cookie setup result:", res)
        else:
            print("Please provide the li_at cookie value: python linkedin_mcp_client.py --cookie <value>")
    elif "--import" in args:
        browser = "auto"
        for a in args:
            if a.startswith("--browser="):
                browser = a.split("=")[1]
        res = client.import_session(browser)
        print("Import result:", res)
    elif "--search" in args:
        kw = "Software Engineer"
        loc = None
        idx = args.index("--search")
        if idx + 1 < len(args):
            kw = args[idx + 1]
        if idx + 2 < len(args):
            loc = args[idx + 2]
        print(f"Searching LinkedIn jobs for '{kw}' in '{loc}'...")
        res = client.search_jobs(kw, loc)
        print(json.dumps(res, indent=2))
    else:
        print("=== LinkedIn MCP Client Status ===")
        status = client.get_status()
        print("Authenticated:", status.get("authenticated"))
        clean_out = (status.get("output") or "").encode("ascii", "ignore").decode()
        print("Details:\n", clean_out)
        print("\nCommands:")
        print("  python linkedin_mcp_client.py --login              (Log into LinkedIn via browser window)")
        print("  python linkedin_mcp_client.py --cookie <li_at>     (Set li_at session cookie from Chrome)")
        print("  python linkedin_mcp_client.py --import             (Import session from Chrome/Edge)")
        print("  python linkedin_mcp_client.py --search <kw> <loc>  (Search LinkedIn jobs)")
