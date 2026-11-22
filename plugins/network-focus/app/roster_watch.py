"""Watches the roster folder and keeps the answer to "who's new since this week's brief?" (standard library only).
The diff itself runs in roster_diff.py, because reading .xlsx files needs openpyxl."""
import threading
import time
from pathlib import Path
from typing import Callable

from dashboard_data import latest_snapshot_path, roster_dir

ROSTER_SUFFIXES = (".xlsx", ".csv")


def newest_roster(folder: Path) -> Path | None:
    try:
        files = [f for f in Path(folder).iterdir() if f.is_file() and f.suffix.lower() in ROSTER_SUFFIXES
                 and not f.name.startswith(("~$", "."))]
    except OSError:  # Drive signed out or unmounted
        return None
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


class RosterWatch:
    def __init__(self, nf_home: Path, run_diff: Callable[[Path, Path], dict], interval: int = 120):
        self.nf_home, self.run_diff, self.interval = Path(nf_home), run_diff, interval
        self._seen = None      # the newest file's (path, size, mtime_ns) at the last check
        self._diffed = None    # what the cached answer was computed from
        self._changes = None
        self._lock = threading.Lock()

    def check_once(self, now: float) -> None:
        """Look once. A file counts only when it's steady, so a half-saved or half-synced file is never read."""
        try:
            self._check(now)
        except Exception:
            with self._lock:
                self._changes = None

    def _check(self, now: float) -> None:
        roster, snap = newest_roster(roster_dir(self.nf_home)), latest_snapshot_path(self.nf_home)
        if roster is None or snap is None:
            with self._lock:
                self._seen, self._changes = None, None
            return
        st = roster.stat()
        key = (str(roster), st.st_size, st.st_mtime_ns)
        steady = key == self._seen or now - st.st_mtime >= self.interval
        self._seen = key
        if not steady:
            return
        basis = (key, str(snap), snap.stat().st_mtime_ns)
        if basis == self._diffed:
            return
        result = self.run_diff(roster, snap)
        found = isinstance(result, dict) and result.get("ok") and (result.get("new") or result.get("changed"))
        with self._lock:
            self._diffed = basis
            self._changes = {"file": roster.name, "modified": st.st_mtime,
                             "new": result.get("new", []), "changed": result.get("changed", []),
                             "removed": result.get("removed", [])} if found else None

    def state(self) -> dict:
        with self._lock:
            return {"changes": self._changes}

    def start(self) -> None:
        def loop():
            while True:
                self.check_once(time.time())
                time.sleep(self.interval)
        threading.Thread(target=loop, daemon=True).start()
