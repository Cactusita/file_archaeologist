import os
import platform
from pathlib import Path
from typing import Any, Union, List, Tuple, Dict
import ctypes

PathString = Union[str, Path]

FORBIDDEN_CHARS = '/:*?"<>|'
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL",
                  *(f"COM{i}" for i in range(1, 10)),
                  *(f"LPT{i}" for i in range(1, 10))}
MAX_PATH = 260
MAX_RECURSION_DEPTH = 64

FILE_ATTRIBUTE_READONLY = 0x01
FILE_ATTRIBUTE_HIDDEN = 0x02
FILE_ATTRIBUTE_SYSTEM = 0x04
FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_REPARSE_POINT = 0x400  # symlink / junction
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
def is_windows_os() -> bool:
    """Проверка что программа запущена на Windows"""
    return platform.system() == 'Windows'


def _split_prefix(path: str) -> Tuple[str, str]:
    """Отделяет префикс длинного пути (\\\\?\\ или \\\\?\\UNC\\)."""
    for pre in ("\\\\?\\UNC\\", "\\\\?\\"):
        if path.startswith(pre):
            return pre, path[len(pre):]
    return "", path


def validate_windows_path(path: PathString) -> Tuple[bool, str]:
    """Проверка корректности Windows пути"""
    raw = str(path)
    if not raw.strip():
        return False, "Пустой путь"
    prefix, body = _split_prefix(raw)
    if not prefix and len(raw) > MAX_PATH:
        return False, f"Путь длиннее {MAX_PATH} символов"
    _, tail = os.path.splitdrive(body)  # двоеточие диска не проверяем
    bad = sorted({c for c in tail if c in FORBIDDEN_CHARS})
    if bad:
        return False, f"Запрещённые символы: {' '.join(bad)}"
    if not os.path.exists(resolve_long_paths_recursive(raw)):
        return False, "Путь не существует"
    return True, ""

    # TODO: Проверить путь на соответствие правилам Windows
    # - Запрещенные символы: / : * ? " < > |
    # - Длина пути (максимум 260 символов для обычных путей)
    # - Проверка существования пути
    # Вернуть (True, "") если путь валиден, (False, "сообщение об ошибке") если нет
    pass

def format_size(size_bytes: int) -> str:
    """Форматирование размера файла в читаемом виде для Windows"""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            if unit == 'B':
                return f"{size:.0f} B"
            else:
                return f"{size:.1f} {unit}"
        size = size / 1024
    return f"{size:.1f} TB"


def get_parent_path(path: PathString) -> str:
    """Получение родительского каталога с учетом Windows путей"""
    norm = os.path.normpath(str(path))
    drive, tail = os.path.splitdrive(norm)
    if drive and tail in ("", "\\"):
        return drive + "\\"
    return os.path.dirname(norm) or norm


def safe_windows_listdir(path: PathString) -> List[str]:
    """Безопасное получение содержимого каталога в Windows"""
    target = resolve_long_paths_recursive(path)
    try:
        return os.listdir(target)
    except (PermissionError, FileNotFoundError, NotADirectoryError, OSError):
        return []
def get_file_attributes(path: PathString) -> int:
    """Битовая маска атрибутов Windows (0 при ошибке)."""
    target = resolve_long_paths_recursive(path)
    try:
        if is_windows_os():
            attrs = ctypes.windll.kernel32.GetFileAttributesW(target)
            return 0 if attrs == INVALID_FILE_ATTRIBUTES else int(attrs)
        return getattr(os.stat(target), "st_file_attributes", 0)
    except (OSError, AttributeError):
        return 0

def is_hidden_windows_file(path: PathString) -> bool:
    """Проверка является ли файл скрытым в Windows"""
    return bool(get_file_attributes(path) & FILE_ATTRIBUTE_HIDDEN)
    # TODO: Проверить атрибуты файла на наличие FILE_ATTRIBUTE_HIDDEN
    # Использовать os.stat или ctypes для проверки атрибутов Windows
    pass


#------------ 2 STEP

def _check_segment(name: str) -> List[str]:
    """Проблемы одного сегмента пути."""
    problems = []
    bad = sorted({c for c in name if c in FORBIDDEN_CHARS})
    if bad:
        problems.append(f"запрещённые символы {' '.join(bad)}")
    if name.split(".")[0].upper() in RESERVED_NAMES:
        problems.append("зарезервированное имя")
    if name and name[-1] in " .":
        problems.append("имя оканчивается пробелом или точкой")
    return problems


def validate_windows_path_recursive(
        path: PathString, depth: int = 0) -> Tuple[bool, List[str]]:
    """Проверка пути и всех родителей. Возвращает (валиден, проблемы)."""
    if depth > MAX_RECURSION_DEPTH:
        return False, ["превышена максимальная глубина рекурсии"]
    norm = os.path.normpath(str(path))
    parent = get_parent_path(norm)
    problems: List[str] = []
    if parent == norm:  # база рекурсии: корень диска
        return True, problems
    name = os.path.basename(norm)
    problems += [f"{norm}: {p}" for p in _check_segment(name)]
    ok_parent, parent_problems = validate_windows_path_recursive(
        parent, depth + 1)
    problems += parent_problems
    return not problems and ok_parent, problems


def _is_reparse(path: str) -> bool:
    """Symlink / junction - не заходим, чтобы не зациклиться."""
    return bool(get_file_attributes(path) & FILE_ATTRIBUTE_REPARSE_POINT) \
        or os.path.islink(path)


def collect_windows_metadata_recursive(
        path: PathString, max_depth: int = 10, level: int = 0
) -> Dict[str, Any]:
    """Вложенный словарь метаданных каталога.

    Узел: name, path, level, files, dirs, attributes, file_types, children.
    """
    path = str(path)
    node: Dict[str, Any] = {
        "name": os.path.basename(path.rstrip("\\")) or path,
        "path": path, "level": level, "files": 0, "dirs": 0,
        "attributes": {"hidden": 0, "system": 0, "readonly": 0},
        "file_types": {}, "children": [],
    }
    for name in safe_windows_listdir(path):
        full = os.path.join(path, name)
        attrs = get_file_attributes(full)
        for key, flag in (("hidden", FILE_ATTRIBUTE_HIDDEN),
                          ("system", FILE_ATTRIBUTE_SYSTEM),
                          ("readonly", FILE_ATTRIBUTE_READONLY)):
            node["attributes"][key] += bool(attrs & flag)
        if attrs & FILE_ATTRIBUTE_DIRECTORY or os.path.isdir(full):
            node["dirs"] += 1
            if level < max_depth and not _is_reparse(full):
                node["children"].append(collect_windows_metadata_recursive(
                    full, max_depth, level + 1))
        else:
            node["files"] += 1
            ext = os.path.splitext(name)[1].lower() or "(без расширения)"
            node["file_types"][ext] = node["file_types"].get(ext, 0) + 1
    return node


def resolve_long_paths_recursive(path: PathString,
                                 prefix: str = "\\\\?\\") -> str:
    """Добавляет \\\\?\\ (или \\\\?\\UNC\\) к путям >= 260 символов."""
    raw = str(path)
    if raw.startswith(prefix) or not is_windows_os():
        return raw
    full = os.path.abspath(raw)
    if len(full) < MAX_PATH:
        return full
    if full.startswith("\\\\"):  # UNC: \\server\share -> \\?\UNC\server\share
        return prefix + "UNC\\" + full[2:]
    return prefix + full