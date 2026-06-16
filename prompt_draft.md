# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview

Audit and refactor the ORANGE OS kernel codebase to automatically resolve note paths in subdirectories, find and fix all similar path resolution or file access bugs, and generate a comprehensive audit report.

Working directory: C:\orange
Integrity mode: development

## Requirements

### R1. Automatic Subdirectory Path Resolution
The system must automatically search and resolve the relative path of a note inside subdirectories of the Obsidian vault if it is not found at the root. Specifically, update `read_file_fast` in `core/tools.py`.
- **Duplicate Rule**: If duplicate note names exist in different subdirectories, resolve to the first match automatically.

### R2. Codebase Audit and Refactoring
Conduct a full audit of the codebase to identify any similar issues where file operations (reading, writing, deleting, or updating status via CLI) assume the note resides at the vault root and fail if it is in a subdirectory. Refactor these locations to be subdirectory-aware.

### R3. Validation and Testing
Ensure all existing tests in `scratch/test_bugfixes.py` continue to pass successfully.

### R4. Completion Report
Create a final markdown report `audit_report.md` in the workspace root detailing all audited files, discovered bugs, and applied fixes.

## Acceptance Criteria

### Functionality
- [ ] Notes in subfolders (e.g. `ежедневник/2025-11-15.md`) can be read via `read_file_fast` by specifying just the note name `2025-11-15` or `2025-11-15.md`.
- [ ] No path-resolution bugs remain in the other core modules.
- [ ] All 6 tests in `scratch/test_bugfixes.py` pass.
- [ ] A final audit report file `audit_report.md` is generated in the workspace root.
