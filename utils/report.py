from pathlib import Path
from datetime import datetime


REPORT_DIR = Path.home() / "Documents" / "Notes" / "Ventoz" / "Reference"
MASTER_PATH = REPORT_DIR / "HardwareSurvey.md"


def _ensure_dir():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def get_report_path():
    _ensure_dir()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return REPORT_DIR / f"HardwareSurvey_{timestamp}.md"


def write_report(content: str) -> Path:
    report_path = get_report_path()
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)
    return report_path


def write_master_report(content: str) -> Path:
    _ensure_dir()
    with open(MASTER_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    return MASTER_PATH
