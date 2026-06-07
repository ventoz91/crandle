import json
import re
from pathlib import Path
from datetime import datetime


# Matches only timestamped survey archives — never diff files or the master
_ARCHIVE_RE = re.compile(r"^HardwareSurvey_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2})\.md$")


REPORT_DIR = Path.home() / "Documents" / "Notes" / "Ventoz" / "Reference"
ARCHIVE_DIR = REPORT_DIR / "Hardware Historic"
MASTER_PATH = REPORT_DIR / "HardwareSurvey.md"


def md_escape(s: str) -> str:
    """Escape a value for safe embedding in a markdown table cell."""
    return str(s).replace("|", "\\|").replace("\n", " ")


def _ensure_dirs():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def report_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M")


def get_report_path(timestamp: str | None = None) -> Path:
    _ensure_dirs()
    return ARCHIVE_DIR / f"HardwareSurvey_{timestamp or report_timestamp()}.md"


def write_report(content: str, timestamp: str | None = None) -> Path:
    report_path = get_report_path(timestamp)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)
    return report_path


def write_json_report(hosts: list, timestamp: str | None = None) -> Path:
    """Write raw collected data for every scanned host as a timestamped JSON
    archive — same naming/timestamp scheme as write_report so the two pair up."""
    _ensure_dirs()
    timestamp = timestamp or report_timestamp()
    json_path = ARCHIVE_DIR / f"HardwareSurvey_{timestamp}.json"
    payload = {"timestamp": timestamp, "hosts": hosts}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return json_path


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


def _sorted_archives() -> list[Path]:
    _ensure_dirs()
    matched = [(m.group(1), p) for p in ARCHIVE_DIR.iterdir() if (m := _ARCHIVE_RE.match(p.name))]
    return [p for _, p in sorted(matched)]


def get_previous_archive() -> Path | None:
    """Return the second-most-recent archive — the one before the current master was written."""
    archives = _sorted_archives()
    return archives[-2] if len(archives) >= 2 else None


def write_diff_report(content: str) -> Path:
    _ensure_dirs()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    diff_path = ARCHIVE_DIR / f"HardwareSurveyDiff_{timestamp}.md"
    with open(diff_path, "w", encoding="utf-8") as f:
        f.write(content)
    return diff_path
