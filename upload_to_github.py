import os
import sys
import base64
import requests

def upload_project_to_github(token: str, repo_name: str = "jobflow-ai", is_private: bool = False):
    print("=" * 65)
    print("GITHUB AUTOMATED REPO CREATION & DEPLOYMENT")
    print("=" * 65)

    if not token or not token.strip():
        print("ERROR: GitHub Personal Access Token is required.")
        print("Generate one in 30 seconds at: https://github.com/settings/tokens")
        print("Select scope: 'repo' (Full control of private/public repositories)")
        sys.exit(1)

    token = token.strip()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    # 1. Get authenticated user
    print("\n[1/4] Verifying GitHub user credentials...")
    user_res = requests.get("https://api.github.com/user", headers=headers, timeout=10)
    if user_res.status_code != 200:
        print(f"ERROR: GitHub authentication failed: {user_res.status_code} {user_res.text}")
        sys.exit(1)
    
    username = user_res.json().get("login")
    print(f"Authenticated as GitHub user: @{username}")

    # 2. Create Repository
    print(f"\n[2/4] Creating repository '{username}/{repo_name}'...")
    create_res = requests.post(
        "https://api.github.com/user/repos",
        headers=headers,
        json={
            "name": repo_name,
            "description": "JobFlow AI - 24/7 Automated Job Search & Application Platform",
            "private": is_private,
            "auto_init": True
        },
        timeout=15
    )
    if create_res.status_code in [200, 201]:
        print(f"Repository created: https://github.com/{username}/{repo_name}")
    elif create_res.status_code == 422:
        print(f"Repository already exists, updating contents...")
    else:
        print(f"ERROR creating repository: {create_res.status_code} {create_res.text}")
        sys.exit(1)

    # 3. Get base commit & tree
    ref_res = requests.get(
        f"https://api.github.com/repos/{username}/{repo_name}/git/refs/heads/main",
        headers=headers,
        timeout=10
    )
    if ref_res.status_code != 200:
        # Check master branch fallback
        ref_res = requests.get(
            f"https://api.github.com/repos/{username}/{repo_name}/git/refs/heads/master",
            headers=headers,
            timeout=10
        )
    
    if ref_res.status_code != 200:
        print(f"ERROR getting branch ref: {ref_res.status_code} {ref_res.text}")
        sys.exit(1)

    base_commit_sha = ref_res.json()["object"]["sha"]
    branch_ref_url = ref_res.json()["url"]

    # 4. Upload all files
    print("\n[3/4] Preparing and uploading project files...")
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    
    tree_items = []
    
    ignore_files = {
        "cloudflared.exe", "huggingface_hub", "jobflow-ai.zip", "test_e2e_verification.py",
        "verify_security_isolation.py"
    }
    ignore_extensions = {".exe", ".pyc", ".log"}
    ignore_dirs = {"__pycache__", ".git", ".pytest_cache", ".gemini", "env", "venv", ".venv"}

    for root, dirs, files in os.walk(workspace_dir):
        # Filter out ignored directories
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]

        for f in files:
            if f in ignore_files or any(f.endswith(ext) for ext in ignore_extensions):
                continue
            
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, workspace_dir).replace("\\", "/")
            
            try:
                with open(full_path, "rb") as fl:
                    content_bytes = fl.read()
                
                # Create blob
                b64_content = base64.b64encode(content_bytes).decode("utf-8")
                blob_res = requests.post(
                    f"https://api.github.com/repos/{username}/{repo_name}/git/blobs",
                    headers=headers,
                    json={"content": b64_content, "encoding": "base64"},
                    timeout=15
                )
                if blob_res.status_code == 201:
                    tree_items.append({
                        "path": rel_path,
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_res.json()["sha"]
                    })
                else:
                    print(f"Warning: Failed to create blob for {rel_path}")
            except Exception as e:
                print(f"Skipping {rel_path}: {e}")

    print(f"Created {len(tree_items)} file blobs successfully.")

    # Create new tree
    tree_res = requests.post(
        f"https://api.github.com/repos/{username}/{repo_name}/git/trees",
        headers=headers,
        json={"base_tree": base_commit_sha, "tree": tree_items},
        timeout=20
    )
    if tree_res.status_code != 201:
        print(f"ERROR creating tree: {tree_res.status_code} {tree_res.text}")
        sys.exit(1)
    new_tree_sha = tree_res.json()["sha"]

    # Create commit
    commit_res = requests.post(
        f"https://api.github.com/repos/{username}/{repo_name}/git/commits",
        headers=headers,
        json={
            "message": "Deploy JobFlow AI website with multi-source search and strict experience filtering",
            "tree": new_tree_sha,
            "parents": [base_commit_sha]
        },
        timeout=15
    )
    if commit_res.status_code != 201:
        print(f"ERROR creating commit: {commit_res.status_code} {commit_res.text}")
        sys.exit(1)
    new_commit_sha = commit_res.json()["sha"]

    # Update branch ref
    update_res = requests.patch(
        branch_ref_url,
        headers=headers,
        json={"sha": new_commit_sha},
        timeout=15
    )
    if update_res.status_code != 200:
        print(f"ERROR updating ref: {update_res.status_code} {update_res.text}")
        sys.exit(1)

    print("\n[4/4] SUCCESS! Code successfully published to GitHub.")
    print("=" * 65)
    print(f"GitHub Repository: https://github.com/{username}/{repo_name}")
    print("\nCLICK THIS 1-CLICK LINK TO DEPLOY TO RENDER (100% FREE):")
    print(f"https://render.com/deploy?repo=https://github.com/{username}/{repo_name}")
    print("=" * 65)

if __name__ == "__main__":
    token = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_TOKEN", "")
    upload_project_to_github(token)
