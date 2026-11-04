"""
Chrome Browser MCP Client
Interfaces with the user's real, live Google Chrome browser via @browsermcp/mcp.
Enables running actions, navigating, scraping, and searching LinkedIn directly within the user's authenticated Chrome profile.
"""

import sys
import os
import json
import subprocess
from typing import Dict, Any, List, Optional

class ChromeBrowserClient:
    def __init__(self):
        pass

    def run_commands(self, commands: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute one or more commands in Chrome via Browser MCP JSON-RPC."""
        proc = subprocess.Popen(
            ["cmd.exe", "/c", "npx", "-y", "@browsermcp/mcp@latest"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8"
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
                    "clientInfo": {"name": "jobflow-chrome-client", "version": "1.0"}
                }
            }
            proc.stdin.write(json.dumps(init_req) + "\n")
            proc.stdin.flush()
            init_line = proc.stdout.readline()
            if not init_line:
                return {"error": "Failed to initialize Browser MCP"}

            # 2. Initialized
            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            proc.stdin.flush()

            # 3. Call tool
            call_req = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "browser",
                    "arguments": {"commands": commands}
                }
            }
            proc.stdin.write(json.dumps(call_req) + "\n")
            proc.stdin.flush()

            resp_line = proc.stdout.readline()
            if not resp_line:
                return {"error": "No response from Browser MCP"}

            data = json.loads(resp_line)
            if "error" in data:
                return {"error": data["error"]}

            result = data.get("result", {})
            content = result.get("content", [])
            text_out = ""
            if content and isinstance(content, list):
                text_out = content[0].get("text", "")

            return {
                "success": not result.get("isError", False),
                "output": text_out,
                "raw": result
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                pass

    def get_tabs(self) -> Dict[str, Any]:
        """List open tabs in Chrome."""
        return self.run_commands("tab list")

    def search_linkedin_jobs(self, keywords: str, location: str = "India") -> Dict[str, Any]:
        """Search jobs on LinkedIn directly in user's active Chrome session and extract job listings."""
        url = f"https://www.linkedin.com/jobs/search/?keywords={keywords.replace(' ', '%20')}&location={location.replace(' ', '%20')}"
        
        # JS snippet to extract job cards from LinkedIn (uses single quotes only)
        extract_js = (
            "() => {"
            "  const items = [];"
            "  const cards = document.querySelectorAll('li.jobs-search-results__list-item, div.job-card-container, div[data-job-id], div.base-card');"
            "  cards.forEach(el => {"
            "    const titleEl = el.querySelector('a.job-card-list__title--link, a.job-card-container__link, strong, h3');"
            "    const compEl = el.querySelector('.artdeco-entity-lockup__subtitle, .job-card-container__primary-description, h4');"
            "    const locEl = el.querySelector('.job-card-container__metadata-item, .artdeco-entity-lockup__caption');"
            "    const linkEl = el.querySelector('a[href*=\\'/jobs/view/\\']') || el.querySelector('a');"
            "    const title = titleEl ? titleEl.innerText.trim() : '';"
            "    const company = compEl ? compEl.innerText.trim() : 'N/A';"
            "    const loc = locEl ? locEl.innerText.trim() : 'N/A';"
            "    const link = linkEl ? linkEl.href : '';"
            "    if (title && title.length > 2 && !items.some(x => x.title === title && x.company === company)) {"
            "      items.push({ title, company, location: loc, link });"
            "    }"
            "  });"
            "  return items.slice(0, 15);"
            "}"
        )
        # Ensure zero double quotes inside the JS function
        extract_js_clean = extract_js.replace('"', "'")
        
        cmds = (
            f"tab new {url}\n"
            "wait 4000\n"
            "scroll down 500\n"
            "wait 2000\n"
            f"eval \"{extract_js_clean}\""
        )
        
        raw_res = self.run_commands(cmds)
        output = raw_res.get("output", "")
        
        # Try to parse JSON from eval output
        parsed_jobs = []
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                try:
                    parsed_jobs = json.loads(line)
                    break
                except Exception:
                    pass
        
        return {
            "success": raw_res.get("success", False),
            "url": url,
            "jobs": parsed_jobs,
            "raw_output": output
        }

def safe_print(text: Any):
    try:
        print(text)
    except UnicodeEncodeError:
        print(str(text).encode("ascii", "ignore").decode())

if __name__ == "__main__":
    client = ChromeBrowserClient()
    args = sys.argv[1:]
    if "--tabs" in args or not args:
        print("=== Chrome Tabs ===")
        res = client.get_tabs()
        safe_print(res.get("output", res))
    elif "--search" in args:
        kw = args[args.index("--search") + 1] if len(args) > args.index("--search") + 1 else "Python Developer"
        loc = args[args.index("--search") + 2] if len(args) > args.index("--search") + 2 else "India"
        print(f"Searching LinkedIn in Chrome for '{kw}' in '{loc}'...")
        res = client.search_linkedin_jobs(kw, loc)
        jobs = res.get("jobs", [])
        if jobs:
            print(f"\nFound {len(jobs)} LinkedIn Jobs:")
            for i, j in enumerate(jobs, 1):
                print(f"{i}. {j.get('title')} at {j.get('company')} ({j.get('location')})")
                print(f"   Link: {j.get('link')}")
        else:
            print("Raw response:")
            safe_print(res.get("raw_output", res))
    elif "--cmd" in args:
        cmd_str = " ".join(args[args.index("--cmd") + 1:])
        res = client.run_commands(cmd_str)
        safe_print(res.get("output", res))
