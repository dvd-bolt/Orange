import os
import subprocess
import datetime
import asyncio
import threading
import re

GIT_SECRET_PATTERN = re.compile(
    r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@|"
    r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
)


def _safe_git_error(value: str, vault_path: str = "") -> str:
    text = str(value or "").strip()
    if vault_path:
        text = text.replace(os.path.abspath(vault_path), "[VAULT]")
    text = GIT_SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}[REDACTED]@" if match.group(1) else "[REDACTED]",
        text,
    )
    return text[:1000]

def run_git_command_sync(cwd: str, args: list[str]) -> tuple[int, str, str]:
    """Runs a git command synchronously in the specified directory."""
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=60,
        )
        return res.returncode, res.stdout, res.stderr
    except Exception as e:
        return -1, "", f"Failed to execute git command: {str(e)}"

_backup_thread_lock = threading.Lock()

def _sync_git_backup(vault_path: str, push: bool = False) -> dict:
    """Synchronous core for git backup, protected by thread lock."""
    with _backup_thread_lock:
        vault_path = os.path.abspath(vault_path)
        if not os.path.isdir(vault_path):
            return {
                "status": "error",
                "error_code": "NOT_CONFIGURED",
                "message": "Vault directory is not configured or unavailable.",
            }
            
        git_dir = os.path.join(vault_path, ".git")
        
        # 1. Initialize git if not present
        if not os.path.exists(git_dir):
            print("[GitBackup] Initializing vault git repository.")
            code, out, err = run_git_command_sync(vault_path, ["init"])
            if code != 0:
                return {"status": "error", "message": f"git init failed: {_safe_git_error(err, vault_path)}"}
                
            # Create a default .gitignore to avoid committing SQLite DBs and temporary backups
            gitignore_path = os.path.join(vault_path, ".gitignore")
            if not os.path.exists(gitignore_path):
                with open(gitignore_path, "w", encoding="utf-8") as f:
                    f.write(".orange/*.db\n.orange/*.db-journal\n*.tmp\n*.bak\n")
                print("[GitBackup] Created default .gitignore in vault")

        # 2. Check for changes before touching the index
        code, out, err = run_git_command_sync(vault_path, ["status", "--porcelain"])
        if code != 0:
            return {"status": "error", "message": f"git status failed: {_safe_git_error(err, vault_path)}"}
            
        if not out.strip():
            print("[GitBackup] No changes to commit.")
            return {"status": "no_changes", "message": "No changes to commit."}

        # 3. Stage changes
        code, out, err = run_git_command_sync(vault_path, ["add", "."])
        if code != 0:
            return {"status": "error", "message": f"git add failed: {_safe_git_error(err, vault_path)}"}

        # 4. Commit changes without changing repository identity configuration
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_msg = f"Orange OS Auto-Backup: {timestamp}"
        code, out, err = run_git_command_sync(vault_path, ["commit", "-m", commit_msg])
        if code != 0:
            err_lower = err.lower()
            if "identity" in err_lower or "tell me who you are" in err_lower:
                return {
                    "status": "error",
                    "error_code": "NOT_CONFIGURED",
                    "message": "Git user.name/user.email are not configured for this vault repository.",
                }
            return {"status": "error", "message": f"git commit failed: {_safe_git_error(err, vault_path)}"}

        print(f"[GitBackup] Committed successfully: {commit_msg}")

        if not push:
            return {"status": "success_local_only", "message": "Committed changes locally. Push is disabled."}

        # 5. Check if remote exists and push was explicitly requested
        code, out, err = run_git_command_sync(
            vault_path,
            ["remote", "get-url", "origin"],
        )
        if code == 0 and out.strip():
            # Get current branch name
            code_br, out_br, err_br = run_git_command_sync(vault_path, ["branch", "--show-current"])
            branch = out_br.strip() if code_br == 0 else ""
            if not branch:
                return {
                    "status": "success_local_only",
                    "message": "Committed locally. Push skipped because HEAD is detached.",
                }
            
            print(f"[GitBackup] Pushing changes to remote branch {branch}...")
            # Push to remote branch
            code_p, out_p, err_p = run_git_command_sync(vault_path, ["push", "origin", branch])
            if code_p != 0:
                print(f"[GitBackup Warning] git push failed: {_safe_git_error(err_p, vault_path)}")
                return {
                    "status": "success_local_only",
                    "message": f"Committed locally, but push failed: {_safe_git_error(err_p, vault_path)}",
                }
            else:
                print("[GitBackup] Pushed successfully.")
                return {"status": "success", "message": f"Committed and pushed successfully to remote branch {branch}."}
                
        return {"status": "success_local_only", "message": "Committed changes locally. No remote configured."}

async def auto_backup_vault(vault_path: str, push: bool = False) -> dict:
    """
    Initializes git if needed, stages all files, commits changes, and only pushes when push=True.
    """
    # Offload synchronous execution to a separate thread
    return await asyncio.to_thread(_sync_git_backup, vault_path, push)
