import os
import tomllib
from typing import Optional, Tuple

def parse_slash_command(user_prompt: str) -> Optional[Tuple[str, str]]:
    """
    Parses a slash command from the user prompt.
    Returns (command_name, command_text) if it starts with '/', otherwise None.
    Example: "/braindump test message" -> ("braindump", "test message")
    """
    cleaned = user_prompt.strip()
    if not cleaned.startswith("/"):
        return None
        
    parts = cleaned[1:].split(None, 1)
    command_name = parts[0].lower()
    command_text = parts[1] if len(parts) > 1 else ""
    return command_name, command_text

def get_dynamic_instruction(vault_path: str, command_name: str) -> Optional[str]:
    """
    Looks for a command configuration in .orange/commands/command_name.toml
    or a skill profile in .orange/skills/command_name.md.
    Returns the loaded system instruction text or None.
    """
    if not vault_path:
        return None
        
    # 1. Check commands TOML
    toml_path = os.path.join(vault_path, ".orange", "commands", f"{command_name}.toml")
    if os.path.exists(toml_path):
        try:
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
                # Look for typical instruction fields
                for key in ["system_instruction", "system_prompt", "instruction", "prompt", "content"]:
                    if key in data and isinstance(data[key], str):
                        return data[key]
                # Fallback to the first string value in the TOML dictionary
                for val in data.values():
                    if isinstance(val, str):
                        return val
        except Exception as e:
            print(f"[Commands Handler] Error parsing TOML command '{toml_path}': {e}")
            
    # 2. Check skills Markdown
    md_path = os.path.join(vault_path, ".orange", "skills", f"{command_name}.md")
    if os.path.exists(md_path):
        try:
            with open(md_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
        except Exception as e:
            print(f"[Commands Handler] Error reading Markdown skill '{md_path}': {e}")
            
    return None
