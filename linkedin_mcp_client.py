"""
LinkedIn MCP Client
Interfaces with the LinkedIn Model Context Protocol (MCP) server (stickerdaniel/linkedin-mcp-server).
Supports querying live LinkedIn jobs, profiles, companies, and checking session/login status.
"""

import sys
import os
import json
import subprocess
from typing import Dict, Any, List, Optional

UVX_PATH = r"C:\Users\rohit\.local\bin\uvx.exe" if os.path.exists(r"C:\Users\rohit\.local\bin\uvx.exe") else "uvx"

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
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                pass

    def get_status(self) -> Dict[str, Any]:
        """Check if a valid LinkedIn session exists."""
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
