from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator, Optional


class VaultPathError(ValueError):
    """Raised when a requested path cannot be resolved safely inside a vault."""


class AmbiguousVaultPathError(VaultPathError):
    """Raised when a filename-only lookup matches more than one vault note."""


class VaultNotConfiguredError(VaultPathError):
    """Raised when an operation requires a vault directory that is not present."""


class VaultPathResolver:
    """Resolves existing and future paths without allowing vault escapes."""

    default_read_limit = 1_000_000

    def __init__(self, vault_root: str | Path):
        self.root = Path(vault_root).expanduser().resolve(strict=False)

    def ensure_root(self) -> Path:
        if not self.root.is_dir():
            raise VaultNotConfiguredError(f"Vault directory is not configured: {self.root}")
        return self.root

    def resolve(
        self,
        user_path: str | Path,
        *,
        must_exist: bool = False,
        allowed_extensions: Optional[Iterable[str]] = None,
    ) -> Path:
        if user_path is None or not str(user_path).strip():
            raise VaultPathError("Vault path is empty.")

        raw = Path(str(user_path).strip()).expanduser()
        candidate = raw if raw.is_absolute() else self.root / raw
        resolved = candidate.resolve(strict=False)
        self._ensure_inside(resolved, user_path)

        if allowed_extensions is not None:
            allowed = {
                extension.lower() if extension.startswith(".") else f".{extension.lower()}"
                for extension in allowed_extensions
            }
            if resolved.suffix.lower() not in allowed:
                raise VaultPathError(
                    f"Unsupported vault file extension '{resolved.suffix or '<none>'}'."
                )

        if must_exist and not resolved.exists():
            raise VaultPathError(f"Vault path does not exist: {user_path}")
        return resolved

    def resolve_note(
        self,
        user_path: str | Path,
        *,
        must_exist: bool = False,
        search_by_name: bool = False,
    ) -> Path:
        raw_value = str(user_path).strip()
        candidate = self.resolve(raw_value)

        if candidate.suffix.lower() != ".md":
            with_suffix = self.resolve(f"{raw_value}.md")
            if with_suffix.exists() or not candidate.exists():
                candidate = with_suffix

        if candidate.exists() or not search_by_name:
            if must_exist and not candidate.is_file():
                raise VaultPathError(f"Vault note does not exist: {user_path}")
            return candidate

        filename = candidate.name.lower()
        matches = []
        for path in self.root.rglob("*.md"):
            if self._is_hidden(path) or path.name.lower() != filename:
                continue
            try:
                match = path.resolve(strict=False)
                self._ensure_inside(match, user_path)
            except (OSError, VaultPathError):
                continue
            matches.append(match)
        matches.sort(key=lambda path: path.as_posix().casefold())

        if len(matches) > 1:
            relative = ", ".join(str(path.relative_to(self.root)) for path in matches[:5])
            raise AmbiguousVaultPathError(
                f"Vault note name is ambiguous: {user_path}. Matches: {relative}"
            )
        if matches:
            return matches[0]
        if must_exist:
            raise VaultPathError(f"Vault note does not exist: {user_path}")
        return candidate

    def relative(self, path: str | Path) -> str:
        resolved = self.resolve(path)
        return resolved.relative_to(self.root).as_posix()

    def iter_notes(
        self,
        *,
        exclude_generated: bool = False,
        include_hidden: bool = False,
    ) -> Iterator[Path]:
        """Yield path-safe Markdown files in deterministic vault-relative order."""
        if not self.root.is_dir():
            return

        safe_paths = []
        for raw_path in self.root.rglob("*.md"):
            try:
                resolved = self.resolve_note(raw_path, must_exist=True)
                relative = resolved.relative_to(self.root)
            except (OSError, VaultPathError):
                continue
            if not resolved.is_file():
                continue
            if not include_hidden and any(part.startswith(".") for part in relative.parts):
                continue
            if exclude_generated and "_orange" in {part.lower() for part in relative.parts}:
                continue
            safe_paths.append((relative.as_posix().lower(), resolved))

        for _, path in sorted(safe_paths, key=lambda item: item[0]):
            yield path

    def read_note_text(
        self,
        user_path: str | Path,
        *,
        max_chars: int = default_read_limit,
    ) -> str:
        path = self.resolve_note(user_path, must_exist=True)
        with path.open("r", encoding="utf-8", errors="ignore") as file:
            return file.read(max(1, int(max_chars)))

    def is_inside(self, path: str | Path) -> bool:
        try:
            self.resolve(path)
            return True
        except VaultPathError:
            return False

    def _ensure_inside(self, path: Path, original: object) -> None:
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise VaultPathError(f"Path is outside the vault: {original}") from exc

    def _is_hidden(self, path: Path) -> bool:
        try:
            parts = path.relative_to(self.root).parts
        except ValueError:
            return True
        return any(part.startswith(".") for part in parts)
