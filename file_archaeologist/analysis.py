import os
from typing import Any, Dict, Tuple

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

def _walk(path: str, depth: int = 0) -> list:

    result = []
    if depth > MAX_DEPTH:
        return result
    ok, items = navigation.list_directory(path)
    if not ok:
        return result
    for item in items:
        full = os.path.join(path, item["name"])
        if item["type"] in ("dir", "directory"):
            if os.path.islink(full) or _attrs(full) & REPARSE:
                continue
            result.append(("dir", full, item))
            result += _walk(full, depth + 1)
        else:
            result.append(("file", full, item))
    return result


def count_files(path: str) -> Tuple[bool, int]:

    if not navigation.list_directory(path)[0]:
        return False, 0
    return True, sum(1 for kind, _, _ in _walk(path) if kind == "file")


def count_bytes(path: str) -> Tuple[bool, int]:

    if not navigation.list_directory(path)[0]:
        return False, 0
    return True, sum(i.get("size", 0) for k, _, i in _walk(path)
                     if k == "file")


def analyze_windows_file_types(
        path: str) -> Tuple[bool, Dict[str, Dict[str, Any]]]:

    if not navigation.list_directory(path)[0]:
        return False, {}
    stats = {}
    for kind, _, item in _walk(path):
        if kind == "file":
            ext = os.path.splitext(item["name"])[1].lower()
            if ext not in stats:
                stats[ext] = {"count": 0, "total_size": 0}
            stats[ext]["count"] += 1
            stats[ext]["total_size"] += item.get("size", 0)
    return True, stats


def get_windows_file_attributes_stats(path: str) -> Dict[str, int]:

    res = {"hidden": 0, "system": 0, "readonly": 0}
    for _, full, item in _walk(path):
        attrs = _attrs(full)
        res["hidden"] += bool(item.get("hidden") or attrs & HIDDEN)
        res["system"] += bool(attrs & SYSTEM)
        res["readonly"] += bool(attrs & READONLY)
    return res


def show_windows_directory_stats(path: str) -> bool:

    ok, files = count_files(path)
    if not ok:
        print(f"Не удалось прочитать: {path}")
        return False
    _, total = count_bytes(path)
    _, types = analyze_windows_file_types(path)
    attrs = get_windows_file_attributes_stats(path)

    dirs = 0
    big = []
    for kind, full, item in _walk(path):
        if kind == "dir":
            dirs += 1
        else:
            big.append((item.get("size", 0), full))
    big.sort(reverse=True)

    print(f"Файлов: {files}, папок: {dirs}")
    print(f"Размер: {utils.format_size(total)}")

    print("Типы файлов (топ-5 по размеру):")
    rows = []
    for ext, data in types.items():
        rows.append((data["total_size"], ext, data["count"]))
    rows.sort(reverse=True)
    for size, ext, count in rows[:5]:
        print(f"  {ext}: {count} шт., {utils.format_size(size)}")

    print("Атрибуты:", attrs)

    print("Крупнейшие файлы:")
    for size, full in big[:5]:
        print(f"  {utils.format_size(size)}  {full}")
    return True
