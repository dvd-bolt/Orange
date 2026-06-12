import os
import subprocess
import datetime
import asyncio
import threading

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
            errors='ignore'
        )
        return res.returncode, res.stdout, res.stderr
    except Exception as e:
        return -1, "", f"Failed to execute git command: {str(e)}"

_backup_thread_lock = threading.Lock()

def _sync_git_backup(vault_path: str) -> dict:
    """Synchronous core for git backup, protected by thread lock."""
    with _backup_thread_lock:
        vault_path = os.path.abspath(vault_path)
        if not os.path.isdir(vault_path):
            return {"status": "error", "message": f"Vault path {vault_path} is not a directory."}
            
        git_dir = os.path.join(vault_path, ".git")
        
        # 1. Initialize git if not present
        if not os.path.exists(git_dir):
            print(f"[GitBackup] Initializing git repository in {vault_path}")
            code, out, err = run_git_command_sync(vault_path, ["init"])
            if code != 0:
                return {"status": "error", "message": f"git init failed: {err}"}
                
            # Create a default .gitignore to avoid committing SQLite DBs and temporary backups
            gitignore_path = os.path.join(vault_path, ".gitignore")
            if not os.path.exists(gitignore_path):
                with open(gitignore_path, "w", encoding="utf-8") as f:
                    f.write(".orange/*.db\n.orange/*.db-journal\n*.tmp\n*.bak\n")
                print("[GitBackup] Created default .gitignore in vault")

        # 2. Stage changes
        code, out, err = run_git_command_sync(vault_path, ["add", "."])
        if code != 0:
            return {"status": "error", "message": f"git add failed: {err}"}

        # 3. Check status
        code, out, err = run_git_command_sync(vault_path, ["status", "--porcelain"])
        if code != 0:
            return {"status": "error", "message": f"git status failed: {err}"}
            
        if not out.strip():
            print("[GitBackup] No changes to commit.")
            return {"status": "no_changes", "message": "No changes to commit."}

        # 4. Commit changes
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_msg = f"Orange OS Auto-Backup: {timestamp}"
        code, out, err = run_git_command_sync(vault_path, ["commit", "-m", commit_msg])
        if code != 0:
            # Check if it was because of git config (name/email not set)
            err_lower = err.lower()
            if "identity" in err_lower or "tell me who you are" in err_lower:
                # Configure a dummy user name and email locally for the vault repo
                run_git_command_sync(vault_path, ["config", "user.name", "OrangeAgent"])
                run_git_command_sync(vault_path, ["config", "user.email", "agent@orange.os"])
                # Retry commit
                code, out, err = run_git_command_sync(vault_path, ["commit", "-m", commit_msg])
                if code != 0:
                    return {"status": "error", "message": f"git commit failed after configuring user: {err}"}
            else:
                return {"status": "error", "message": f"git commit failed: {err} (out: {out})"}

        print(f"[GitBackup] Committed successfully: {commit_msg}")

        # 5. Check if remote exists
        code, out, err = run_git_command_sync(vault_path, ["remote"])
        if code == 0 and out.strip():
            # Get current branch name
            code_br, out_br, err_br = run_git_command_sync(vault_path, ["branch", "--show-current"])
            branch = out_br.strip() if code_br == 0 and out_br.strip() else "main"
            
            print(f"[GitBackup] Pushing changes to remote branch {branch}...")
            # Push to remote branch
            code_p, out_p, err_p = run_git_command_sync(vault_path, ["push", "origin", branch])
            if code_p != 0:
                print(f"[GitBackup Warning] git push failed: {err_p}")
                return {"status": "success_local_only", "message": f"Committed locally, but push failed: {err_p}"}
            else:
                print("[GitBackup] Pushed successfully.")
                return {"status": "success", "message": f"Committed and pushed successfully to remote branch {branch}."}
                
        return {"status": "success_local_only", "message": "Committed changes locally. No remote configured."}

async def auto_backup_vault(vault_path: str) -> dict:
    """
    Initializes git if needed, stages all files, commits changes, and pushes if remote is set.
    """
    # Offload synchronous execution to a separate thread
    return await asyncio.to_thread(_sync_git_backup, vault_path)
