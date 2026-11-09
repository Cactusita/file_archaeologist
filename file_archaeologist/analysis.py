"""analysis.py: анализ файловой системы Windows (роль 3, короткая версия)."""

import hashlib
import os
import re
import statistics
import time
from collections import defaultdict
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple

import navigation
import utils

MAX_DEPTH = 50
SKIP_DIRS = {"$recycle.bin", "system volume information"}
READONLY, HIDDEN, SYSTEM, REPARSE = 0x1, 0x2, 0x4, 0x400


def _attrs(path: str) -> int:
    """Число с атрибутами Windows (0, если не удалось прочитать)."""
    try:
        return getattr(os.lstat(path), "st_file_attributes", 0)
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


# ------------------------------ ЭТАП II -----------------------------
_HASH_CACHE: Dict[Tuple[str, int], str] = {}  # мемоизация хешей


def _sha256(path: str) -> str:
    """Хеш файла, читаем блоками по 64 КБ."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            sha.update(block)
    return sha.hexdigest()


def find_duplicate_files_recursive(
        path: str, checksum_func: Optional[Callable[[str], str]] = None,
        visited: Optional[Set[str]] = None) -> Dict[str, List[str]]:
    """{hash: [пути]} только для групп с 2+ файлами."""
    func = checksum_func or _sha256
    visited = set() if visited is None else visited
    by_size: Dict[int, List[str]] = defaultdict(list)
    for kind, full, item in _walk(path):  # 1) группируем по размеру
        if kind == "file" and full not in visited and item.get("size", 0):
            visited.add(full)
            by_size[item["size"]].append(full)
    groups: Dict[str, List[str]] = defaultdict(list)
    for size, paths in by_size.items():  # 2) хешируем только совпавшие
        if len(paths) > 1:
            for p in paths:
                try:
                    key = (p, size)
                    _HASH_CACHE.setdefault(key, func(p))
                    groups[_HASH_CACHE[key]].append(p)
                except OSError:
                    pass
    return {h: p for h, p in groups.items() if len(p) > 1}


def analyze_file_dependencies_recursive(
        root_path: str, target_extensions: Optional[List[str]] = None,
        dependency_tree: Optional[Dict[str, List[str]]] = None
) -> Dict[str, Any]:
    """Граф #include и циклические зависимости."""
    exts = tuple(target_extensions or [".c", ".cpp", ".h", ".hpp"])
    graph = {} if dependency_tree is None else dependency_tree
    names = {os.path.basename(f).lower(): f for k, f, _ in _walk(root_path)
             if k == "file" and f.lower().endswith(exts)}
    for src in names.values():
        try:
            with open(src, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        found = re.findall(r'#\s*include\s*"([^"]+)"', text)
        graph[src] = [names[os.path.basename(i).lower()] for i in found
                      if os.path.basename(i).lower() in names]

    cycles: List[List[str]] = []
    state: Dict[str, int] = {}  # 1 = в обработке, 2 = готово
    stack: List[str] = []

    def dfs(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for dep in graph.get(node, []):
            if state.get(dep) == 1:  # вернулись в вершину: цикл
                cycles.append(stack[stack.index(dep):] + [dep])
            elif dep not in state:
                dfs(dep)
        stack.pop()
        state[node] = 2

    for node in list(graph):
        if node not in state:
            dfs(node)
    return {"tree": graph, "cycles": cycles}


def predict_storage_growth_recursive(
        path: str, days_back: int = 30,
        growth_data: Optional[Dict[str, List[int]]] = None
) -> Dict[str, float]:
    """{папка: МБ в день} по датам изменения файлов (линейная регрессия)."""
    data = {} if growth_data is None else growth_data
    now = time.time()
    root = os.path.abspath(path)
    for kind, full, item in _walk(path):
        if kind != "file":
            continue
        try:
            age = int((now - os.stat(full).st_mtime) // 86400)
        except OSError:
            continue
        if not 0 <= age <= days_back:
            continue
        folder = os.path.dirname(os.path.abspath(full))
        while True:  # добавляем размер во все папки-предки
            data.setdefault(folder, [0] * (days_back + 1))
            data[folder][days_back - age] += item.get("size", 0)
            if folder == root or os.path.dirname(folder) == folder:
                break
            folder = os.path.dirname(folder)
    rates: Dict[str, float] = {}
    for folder, days in data.items():
        total, cumulative = 0, []
        for b in days:
            total += b
            cumulative.append(total / 1048576)  # МБ
        try:
            rates[folder] = statistics.linear_regression(
                range(len(cumulative)), cumulative).slope
        except statistics.StatisticsError:
            rates[folder] = 0.0
    return dict(sorted(rates.items(), key=lambda kv: -kv[1]))