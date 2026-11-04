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
        """Search jobs on LinkedIn directly in user's active Chrome session."""
        url = f"https://www.linkedin.com/jobs/search/?keywords={keywords.replace(' ', '%20')}&location={location.replace(' ', '%20')}"
        cmds = f"tab new {url}\nwait 4000\nget title\nsnapshot -i --depth 5"
        return self.run_commands(cmds)

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
        safe_print(res.get("output", res))
    elif "--cmd" in args:
        cmd_str = " ".join(args[args.index("--cmd") + 1:])
        res = client.run_commands(cmd_str)
        safe_print(res.get("output", res))
