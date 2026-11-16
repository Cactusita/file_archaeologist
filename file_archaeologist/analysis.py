"""analysis.py: анализ файловой системы Windows (роль 3, короткая версия, только I этап)."""

import os
from collections import defaultdict
from typing import Any, Dict, Iterator, Optional, Set, Tuple

import navigation
import utils

MAX_DEPTH = 50
SKIP_DIRS = {"$recycle.bin", "system volume information"}
READONLY, HIDDEN, SYSTEM, REPARSE = 0x1, 0x2, 0x4, 0x400


def _attrs(path: str) -> int:
    try:
        return os.lstat(path).st_file_attributes
    except OSError:
        return 0

def _walk(path: str, depth: int = 0,
          seen: Optional[Set[str]] = None
          ) -> Iterator[Tuple[str, str, Dict[str, Any]]]:
    """Рекурсивный обход: отдаёт (вид, полный_путь, словарь)."""
    seen = set() if seen is None else seen
    key = os.path.normcase(os.path.abspath(path))
    if depth > MAX_DEPTH or key in seen:  # базовый случай
        return
    seen.add(key)
    ok, items = navigation.list_directory(path)
    if not ok:
        return
    for item in items:
        full = os.path.join(path, item["name"])
        if item["type"] in ("dir", "directory"):
            if (item["name"].lower() in SKIP_DIRS or os.path.islink(full)
                    or _attrs(full) & REPARSE):  # junction/symlink
                continue
            yield "dir", full, item
            yield from _walk(full, depth + 1, seen)  # шаг рекурсии
        else:
            yield "file", full, item


# ------------------------------ ЭТАП I ------------------------------
def count_files(path: str) -> Tuple[bool, int]:
    """Число файлов во всех вложенных папках."""
    if not navigation.list_directory(path)[0]:
        return False, 0
    return True, sum(1 for kind, _, _ in _walk(path) if kind == "file")


def count_bytes(path: str) -> Tuple[bool, int]:
    """Суммарный размер файлов в байтах."""
    if not navigation.list_directory(path)[0]:
        return False, 0
    return True, sum(i.get("size", 0) for k, _, i in _walk(path)
                     if k == "file")


def analyze_windows_file_types(
        path: str) -> Tuple[bool, Dict[str, Dict[str, Any]]]:
    """{'.exe': {'count': 3, 'total_size': 1234}, ...}"""
    if not navigation.list_directory(path)[0]:
        return False, {}
    stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "total_size": 0})
    for kind, _, item in _walk(path):
        if kind == "file":
            ext = os.path.splitext(item["name"])[1].lower() or "(нет)"
            stats[ext]["count"] += 1
            stats[ext]["total_size"] += item.get("size", 0)
    return True, dict(stats)


def get_windows_file_attributes_stats(path: str) -> Dict[str, int]:
    """{'hidden': 5, 'system': 2, 'readonly': 10}"""
    res = {"hidden": 0, "system": 0, "readonly": 0}
    for _, full, item in _walk(path):
        attrs = _attrs(full)
        res["hidden"] += bool(item.get("hidden") or attrs & HIDDEN)
        res["system"] += bool(attrs & SYSTEM)
        res["readonly"] += bool(attrs & READONLY)
    return res


def show_windows_directory_stats(path: str) -> bool:
    """Сводный отчёт по каталогу."""
    ok, files = count_files(path)
    if not ok:
        print(f"Не удалось прочитать: {path}")
        return False
    dirs = sum(1 for k, _, _ in _walk(path) if k == "dir")
    print(f"Файлов: {files}, папок: {dirs}, "
          f"размер: {utils.format_size(count_bytes(path)[1])}")
    types = analyze_windows_file_types(path)[1]
    print("Типы (топ-5 по размеру):")
    for ext, d in sorted(types.items(), key=lambda kv: -kv[1]["total_size"])[:5]:
        print(f"  {ext:<10}{d['count']:>6} шт. "
              f"{utils.format_size(d['total_size'])}")
    print("Атрибуты:", get_windows_file_attributes_stats(path))
    big = sorted(((i.get("size", 0), f) for k, f, i in _walk(path)
                  if k == "file"), reverse=True)[:5]
    print("Крупнейшие файлы:")
    for size, full in big:
        print(f"  {utils.format_size(size):>10}  {full}")
    return True