"""Find Google Drive for desktop's "My Drive" folder (standard library only: the installer imports this)."""
from pathlib import Path

FOLDER_NAME = "Network Focus"
_WIN_LETTERS = "DEFGHIJKLMNOPQRSTUVWXYZ"


def find_my_drive(home: Path, system: str, win_roots: list[Path] | None = None) -> list[Path]:
    """Existing "My Drive" folders, best first. Empty when Google Drive for desktop isn't set up."""
    home = Path(home)
    if system == "win32":
        roots = win_roots if win_roots is not None else [Path(f"{c}:\\") for c in _WIN_LETTERS]
        found = []
        for root in roots:
            try:
                if (Path(root) / "My Drive").is_dir():
                    found.append(Path(root) / "My Drive")
            except OSError:  # an empty card reader or a dropped network drive
                continue
        mirror = home / "My Drive"  # "mirror files" mode keeps My Drive in the user folder
        return found + ([mirror] if mirror.is_dir() else [])
    cloud = home / "Library" / "CloudStorage"
    try:
        return sorted(d / "My Drive" for d in cloud.glob("GoogleDrive-*") if (d / "My Drive").is_dir())
    except OSError:
        return []
