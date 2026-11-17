import os
import platform
from pathlib import Path
from typing import List, Tuple, Union

PathString = Union[str, Path]

FORBIDDEN_CHARS = '/:*?"<>|'
MAX_PATH = 260

FILE_ATTRIBUTE_HIDDEN = 0x02
FILE_ATTRIBUTE_SYSTEM = 0x04



def is_windows_os() -> bool:
    """Check that the program is running on Windows."""
    return platform.system() == "Windows"


def _add_long_prefix(path: str) -> str:
    """Adds \\\\?\\ to paths that are 260 characters or longer (UNC: \\\\?\\UNC\\)."""
    prefix = "\\\\?\\"
    if path.startswith(prefix) or not is_windows_os():
        return path
    full = os.path.abspath(path)
    if len(full) < MAX_PATH:
        return full
    if full.startswith("\\\\"):
        return prefix + "UNC\\" + full[2:]
    return prefix + full


def _split_prefix(path: str) -> Tuple[str, str]:
    """Separates the long-path prefix: (prefix, remainder)."""
    for prefix in ("\\\\?\\UNC\\", "\\\\?\\"):
        if path.startswith(prefix):
            return prefix, path[len(prefix):]
    return "", path


def validate_windows_path(path: PathString) -> Tuple[bool, str]:
    """Path validation: characters, length, existence."""
    path_str = str(path)
    if not path_str.strip():
        return False, "Пустой путь"

    prefix, body = _split_prefix(path_str)
    if not prefix and len(path_str) > MAX_PATH:
        return False, f"Путь длиннее {MAX_PATH} символов"

    _, tail = os.path.splitdrive(body)
    bad_chars = sorted({char for char in tail if char in FORBIDDEN_CHARS})
    if bad_chars:
        return False, f"Запрещённые символы: {' '.join(bad_chars)}"

    if not os.path.exists(_add_long_prefix(path_str)):
        return False, "Путь не существует"
    return True, ""


def format_size(size_bytes: int) -> str:
    """Size formatting: 1024 -> '1.0 KB', 1500000 -> '1.4 MB'."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            if unit == "B":
                return f"{size:.0f} B"
            else:
                return f"{size:.1f} {unit}"
        size = size / 1024
    return f"{size:.1f} TB"


def get_parent_path(path: PathString) -> str:
    """Directory parent: C:\\ -> C:\\, C:\\Users -> C:\\."""
    norm = os.path.normpath(str(path))
    drive, tail = os.path.splitdrive(norm)
    if drive and tail in ("", "\\"):
        return drive + "\\"
    return os.path.dirname(norm) or norm


def safe_windows_listdir(path: PathString) -> List[str]:
    """Directory contents; returns an empty list in the event of any error."""
    try:
        return os.listdir(_add_long_prefix(str(path)))
    except PermissionError:  # отказано в доступе
        return []
    except FileNotFoundError:  # каталога нет
        return []
    except OSError:  # длинные пути и прочие ошибки Windows
        return []


def get_file_attributes(path: PathString) -> int:
    """Windows attributes mask (0 on error)."""
    try:
        info = os.lstat(_add_long_prefix(str(path)))
    except OSError:
        return 0
    return getattr(info, "st_file_attributes", 0)



def is_hidden_windows_file(path: PathString) -> bool:
    """Does the file have the FILE_ATTRIBUTE_HIDDEN attribute?"""
    return bool(get_file_attributes(path) & FILE_ATTRIBUTE_HIDDEN)