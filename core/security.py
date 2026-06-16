import os
import sys
import logging
import asyncio
from typing import Dict, Any

logger = logging.getLogger("security")

class SecurityAnalyzer:
    """
    SecurityAnalyzer classifies action risk and blocks unsafe executions.
    """
    def __init__(self, vault_path: str):
        self.vault_path = os.path.abspath(vault_path)

    def analyze_risk(self, action_type: str, details: dict) -> str:
        """
        Classifies action risk level. Returns "LOW", "MEDIUM", or "HIGH".
        Risk classification blocks command execution/file writes outside the vault
        until confirmation is received.
        """
        if action_type == "command_execution":
            cmd = details.get("command", "")
            # High risk commands (e.g. formatting, deleting critical items)
            if any(x in cmd for x in ["rm -rf", "format", "del /", "mkfs"]):
                return "HIGH"
            return "MEDIUM"

        elif action_type == "file_write":
            path = details.get("path", "")
            if not path:
                return "HIGH"
            abs_path = os.path.abspath(path)
            # If path is outside the vault, it is high risk
            if not abs_path.startswith(self.vault_path):
                return "HIGH"
            return "LOW"

        elif action_type == "file_read":
            path = details.get("path", "")
            if not path:
                return "HIGH"
            abs_path = os.path.abspath(path)
            if not abs_path.startswith(self.vault_path):
                return "MEDIUM"
            return "LOW"

        return "LOW"


async def request_override(action_text: str) -> bool:
    """
    Approval request API.
    Pops a PyQt/PySide modal dialog, blocking execution without freezing the UI loop.
    Supports a headless mode via environment variable (ORANGE_TEST_MODE) for automated tests.
    """
    # Check headless/test mode bypass
    if os.environ.get("ORANGE_TEST_MODE") == "1":
        logger.info(f"[Security Gate Bypass] Auto-approving in test mode: {action_text}")
        return True

    # Try importing PyQt/PySide dynamically
    QtWidgets = None
    QtCore = None
    for lib in ["PyQt5", "PySide2", "PySide6", "PyQt6"]:
        try:
            QtWidgets = __import__(f"{lib}.QtWidgets", fromlist=["QApplication", "QDialog", "QVBoxLayout", "QLabel", "QPushButton"])
            QtCore = __import__(f"{lib}.QtCore", fromlist=["Qt"])
            break
        except ImportError:
            continue

    if not QtWidgets or not QtCore:
        logger.warning("[Security Gate] PyQt/PySide not available. Defaulting to console input.")
        # If in terminal (interactive), fallback to stdin check
        loop = asyncio.get_event_loop()
        try:
            # We must run blocking input in thread pool to avoid freezing the event loop
            def ask_input():
                ans = input(f"Approve action? '{action_text}' (y/n): ")
                return ans.strip().lower() in ['y', 'yes']
            return await loop.run_in_executor(None, ask_input)
        except Exception:
            return False

    # Create PyQt dialog
    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication(sys.argv)

    dialog = QtWidgets.QDialog()
    dialog.setWindowTitle("Security Gate Confirmation")
    
    # Resolve window modality dynamically to support different Qt versions
    modality = 2 # default application modal integer
    if QtCore and hasattr(QtCore, "Qt"):
        Qt = QtCore.Qt
        if hasattr(Qt, "ApplicationModal"):
            modality = Qt.ApplicationModal
        elif hasattr(Qt, "WindowModality") and hasattr(Qt.WindowModality, "ApplicationModal"):
            modality = Qt.WindowModality.ApplicationModal
            
    dialog.setWindowModality(modality)
    dialog.setMinimumWidth(400)

    layout = QtWidgets.QVBoxLayout(dialog)
    label = QtWidgets.QLabel(f"An action requires security approval:\n\n{action_text}")
    label.setWordWrap(True)
    layout.addWidget(label)

    approved = [False]

    def on_approve():
        approved[0] = True
        dialog.accept()

    def on_deny():
        approved[0] = False
        dialog.reject()

    btn_approve = QtWidgets.QPushButton("Approve")
    btn_approve.clicked.connect(on_approve)
    layout.addWidget(btn_approve)

    btn_deny = QtWidgets.QPushButton("Deny")
    btn_deny.clicked.connect(on_deny)
    layout.addWidget(btn_deny)

    dialog.setLayout(layout)
    
    # Run in event loop without freezing
    # Using run_in_executor or thread-safe calls to show dialog and block
    loop = asyncio.get_event_loop()
    def show_dialog():
        if hasattr(dialog, "exec"):
            dialog.exec()
        else:
            dialog.exec_()
        
    await loop.run_in_executor(None, show_dialog)
    return approved[0]
