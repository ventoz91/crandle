from pathlib import Path
from datetime import datetime


REPORT_DIR = Path.home() / "Documents" / "Notes" / "Ventoz" / "Reference"
ARCHIVE_DIR = REPORT_DIR / "Hardware Historic"
MASTER_PATH = REPORT_DIR / "HardwareSurvey.md"


def _ensure_dirs():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def get_report_path():
    _ensure_dirs()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return ARCHIVE_DIR / f"HardwareSurvey_{timestamp}.md"


def write_report(content: str) -> Path:
    report_path = get_report_path()
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)
    return report_path


def write_master_report(content: str) -> Path:
    _ensure_dirs()
    with open(MASTER_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    return MASTER_PATH


def read_master_report() -> str | None:
    if not MASTER_PATH.exists():
        return None
    with open(MASTER_PATH, "r", encoding="utf-8") as f:
        return f.read()
