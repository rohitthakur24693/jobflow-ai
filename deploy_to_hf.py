import os
import sys
from huggingface_hub import HfApi

def deploy(token: str, space_name: str = "jobflow-ai"):
    print("=" * 65)
    print("HUGGING FACE SPACES AUTOMATED DEPLOYMENT")
    print("=" * 65)

    if not token or not token.strip():
        print("ERROR: Hugging Face User Access Token is required.")
        print("Get your free token from: https://huggingface.co/settings/tokens (Role: Write)")
        sys.exit(1)

    clean_token = token.strip()
    api = HfApi(token=clean_token)

    try:
        user_info = api.whoami()
        username = user_info.get("name")
        print(f"Authenticated as Hugging Face user: {username}")
    except Exception as e:
        print(f"ERROR: Invalid Hugging Face token: {e}")
        sys.exit(1)

    repo_id = f"{username}/{space_name}"
    print(f"\n[1/3] Creating Space '{repo_id}' with Docker SDK...")
    try:
        space_url = api.create_repo(
            repo_id=repo_id,
            repo_type="space",
            space_sdk="docker",
            exist_ok=True
        )
        print(f"Space created / verified: https://huggingface.co/spaces/{repo_id}")
    except Exception as e:
        print(f"Error creating space: {e}")
        sys.exit(1)

    print("\n[2/3] Uploading project files to Hugging Face Space...")
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    
    ignore_patterns = [
        "*.exe",
        "cloudflared.exe",
        "__pycache__/*",
        "*.pyc",
        "*.log",
        ".git/*",
        ".pytest_cache/*",
        "tokens/gmail_token.json"
    ]

    try:
        api.upload_folder(
            folder_path=workspace_dir,
            repo_id=repo_id,
            repo_type="space",
            ignore_patterns=ignore_patterns,
            commit_message="Deploy JobFlow AI website to Hugging Face Spaces"
        )
        print("Upload completed successfully!")
    except Exception as e:
        print(f"Upload failed: {e}")
        sys.exit(1)

    clean_space = space_name.lower().replace("_", "-")
    direct_app_url = f"https://{username.lower()}-{clean_space}.hf.space"

    print("\n[3/3] Deployment Initiated!")
    print("=" * 65)
    print(f"Space Dashboard: https://huggingface.co/spaces/{repo_id}")
    print(f"Direct Permanent Web URL: {direct_app_url}")
    print("=" * 65)
    print("Hugging Face is building the Docker container now.")
    print("Your website will be live 24/7 with a permanent URL in 1-2 minutes!")

if __name__ == "__main__":
    token = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("HF_TOKEN", "")
    space_name = sys.argv[2] if len(sys.argv) > 2 else "jobflow-ai"
    deploy(token, space_name)
