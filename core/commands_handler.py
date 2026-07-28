import os
import re
import tomllib
from typing import Optional, Tuple
from core.path_safety import VaultPathResolver

COMMAND_NAME_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")

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
    if not COMMAND_NAME_PATTERN.fullmatch(command_name):
        return None
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
        
    if not COMMAND_NAME_PATTERN.fullmatch(command_name):
        return None
    resolver = VaultPathResolver(vault_path)

    # 1. Check commands TOML
    toml_path = resolver.resolve(
        f".orange/commands/{command_name}.toml",
        allowed_extensions={".toml"},
    )
    if toml_path.exists():
        try:
            with toml_path.open("rb") as f:
                data = tomllib.load(f)
                # Look for typical instruction fields
                for key in ["system_instruction", "system_prompt", "instruction", "prompt", "content"]:
                    if key in data and isinstance(data[key], str):
                        return data[key][:32_000]
                # Fallback to the first string value in the TOML dictionary
                for val in data.values():
                    if isinstance(val, str):
                        return val[:32_000]
        except Exception as e:
            print(f"[Commands Handler] Error parsing TOML command '{toml_path}': {e}")
            
    # 2. Check skills Markdown
    md_path = resolver.resolve_note(f".orange/skills/{command_name}.md")
    if md_path.exists():
        try:
            with md_path.open("r", encoding="utf-8", errors="ignore") as f:
                return f.read(32_001).strip()[:32_000]
        except Exception as e:
            print(f"[Commands Handler] Error reading Markdown skill '{md_path}': {e}")
            
    return None
