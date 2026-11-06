"""Модуль analysis: анализ файловой системы Windows (роль 3, Аналитик).

Зависимости: utils.py (Архитектор) и navigation.py (Инженер навигации).

Этап I:  count_files, count_bytes, analyze_windows_file_types,
         get_windows_file_attributes_stats, show_windows_directory_stats.
Этап II: find_duplicate_files_recursive,
         analyze_file_dependencies_recursive,
         predict_storage_growth_recursive.

Главная идея: все функции строятся на одном рекурсивном обходе
``_walk_entries``. Он сам защищается от циклов (junction/symlink),
ошибок доступа, слишком большой глубины и умеет прерываться.
"""

import hashlib
import heapq
import os
import re
import stat
import sys
import threading
import time
from collections import defaultdict
from typing import Any, Callable, Dict, Generator, List, Optional, Set, Tuple

import navigation
import utils

# --------------------------------------------------------------------------
# Константы
# --------------------------------------------------------------------------
DEFAULT_MAX_DEPTH = 100          # защита от переполнения стека
HASH_BLOCK_SIZE = 65536          # читаем файл блоками по 64 КБ
NO_EXTENSION = "(без расширения)"
SECONDS_IN_DAY = 86400

# Атрибуты Windows (на других ОС константы в stat могут отсутствовать)
ATTR_READONLY = getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1)
ATTR_HIDDEN = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0x2)
ATTR_SYSTEM = getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 0x4)
ATTR_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

# Служебные каталоги Windows, в которые не заходим (нижний регистр)
SKIP_DIR_NAMES: Set[str] = {
    "$recycle.bin",
    "system volume information",
    "$windows.~bt",
    "$windows.~ws",
    "config.msi",
}

DIR_TYPES = {"dir", "directory", "folder"}

# --------------------------------------------------------------------------
# Прерывание длительных операций
# --------------------------------------------------------------------------
_cancel_event = threading.Event()


def request_cancel() -> None:
    """Попросить все долгие операции остановиться."""
    _cancel_event.set()


def reset_cancel() -> None:
    """Сбросить флаг отмены перед новой операцией."""
    _cancel_event.clear()


def is_cancelled() -> bool:
    """Проверка, была ли запрошена отмена."""
    return _cancel_event.is_set()


# --------------------------------------------------------------------------
# Внутренние вспомогательные функции
# --------------------------------------------------------------------------
def _get_attributes(path: str) -> int:
    """Атрибуты Windows самого объекта (не цели ссылки). 0 при ошибке."""
    try:
        return getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return 0


def _is_link_or_junction(path: str) -> bool:
    """True для symlink и junction (reparse point): их пропускаем."""
    try:
        if os.path.islink(path):
            return True
        is_junction = getattr(os.path, "isjunction", None)
        if is_junction is not None and is_junction(path):
            return True
    except OSError:
        return True
    return bool(_get_attributes(path) & ATTR_REPARSE)


def _is_dir_item(item: Dict[str, Any]) -> bool:
    """Определяем по словарю из navigation.list_directory, это папка?"""
    return str(item.get("type", "")).lower() in DIR_TYPES


def _item_size(full_path: str, item: Dict[str, Any]) -> int:
    """Размер файла: из словаря navigation, иначе через os.path."""
    size = item.get("size")
    if isinstance(size, int) and size >= 0:
        return size
    try:
        return os.path.getsize(full_path)
    except OSError:
        return 0


def _norm(path: str) -> str:
    """Нормализованный путь для сравнения (регистр в Windows не важен)."""
    return os.path.normcase(os.path.abspath(path))


def _walk_entries(
    path: str,
    max_depth: int = DEFAULT_MAX_DEPTH,
    depth: int = 0,
    visited: Optional[Set[str]] = None,
) -> Generator[Tuple[str, str, Dict[str, Any]], None, None]:
    """Рекурсивный обход. Отдаёт кортежи (вид, полный_путь, словарь).

    вид: "file" или "dir".
    Базовый случай: глубина превышена, каталог уже посещён, отмена
    или каталог недоступен. Шаг рекурсии: спуск в каждую подпапку.
    """
    if visited is None:
        visited = set()
    if depth > max_depth or is_cancelled():
        return
    key = _norm(path)
    if key in visited:
        return
    visited.add(key)

    ok, items = navigation.list_directory(path)
    if not ok:
        return

    for item in items:
        if is_cancelled():
            return
        full = os.path.join(path, str(item.get("name", "")))
        if _is_dir_item(item):
            if str(item.get("name", "")).lower() in SKIP_DIR_NAMES:
                continue
            if _is_link_or_junction(full):
                continue
            yield "dir", full, item
            yield from _walk_entries(full, max_depth, depth + 1, visited)
        else:
            yield "file", full, item


def _root_is_readable(path: str) -> bool:
    """Проверка, что корневой каталог вообще можно прочитать."""
    ok, _ = navigation.list_directory(path)
    return ok


# ==========================================================================
# ЭТАП I
# ==========================================================================
def count_files(path: str) -> Tuple[bool, int]:
    """Рекурсивный подсчёт файлов. (True, число) или (False, 0)."""
    if not _root_is_readable(path):
        return False, 0
    total = sum(
        1 for kind, _, _ in _walk_entries(path) if kind == "file"
    )
    return True, total


def count_bytes(path: str) -> Tuple[bool, int]:
    """Рекурсивная сумма размеров файлов. (True, байты) или (False, 0)."""
    if not _root_is_readable(path):
        return False, 0
    total = 0
    for kind, full, item in _walk_entries(path):
        if kind == "file":
            total += _item_size(full, item)
    return True, total


def analyze_windows_file_types(
    path: str,
) -> Tuple[bool, Dict[str, Dict[str, Any]]]:
    """Статистика по расширениям.

    Результат: {".exe": {"count": 3, "total_size": 12345}, ...}
    Расширения в нижнем регистре (в Windows .EXE == .exe).
    """
    if not _root_is_readable(path):
        return False, {}
    stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "total_size": 0}
    )
    for kind, full, item in _walk_entries(path):
        if kind != "file":
            continue
        ext = os.path.splitext(str(item.get("name", "")))[1].lower()
        ext = ext or NO_EXTENSION
        stats[ext]["count"] += 1
        stats[ext]["total_size"] += _item_size(full, item)
    return True, dict(stats)


def get_windows_file_attributes_stats(path: str) -> Dict[str, int]:
    """Статистика атрибутов: {'hidden': 5, 'system': 2, 'readonly': 10}."""
    result = {"hidden": 0, "system": 0, "readonly": 0}
    if not _root_is_readable(path):
        return result
    for _, full, item in _walk_entries(path):
        attrs = _get_attributes(full)
        if item.get("hidden") or attrs & ATTR_HIDDEN:
            result["hidden"] += 1
        if attrs & ATTR_SYSTEM:
            result["system"] += 1
        if attrs & ATTR_READONLY:
            result["readonly"] += 1
    return result


def _count_dirs(path: str) -> int:
    """Число вложенных папок (для отчёта)."""
    return sum(1 for kind, _, _ in _walk_entries(path) if kind == "dir")


def _largest_files(path: str, limit: int = 10) -> List[Tuple[int, str]]:
    """Крупнейшие файлы: список (размер, путь) по убыванию."""
    candidates = (
        (_item_size(full, item), full)
        for kind, full, item in _walk_entries(path)
        if kind == "file"
    )
    return heapq.nlargest(limit, candidates)


def show_windows_directory_stats(path: str) -> bool:
    """Сводный отчёт по каталогу. True при успехе."""
    reset_cancel()
    try:
        ok_files, files = count_files(path)
        if not ok_files:
            print(f"Не удалось прочитать каталог: {path}")
            return False
        _, total_bytes = count_bytes(path)
        _, types = analyze_windows_file_types(path)
        attrs = get_windows_file_attributes_stats(path)
        dirs = _count_dirs(path)
        largest = _largest_files(path)
    except KeyboardInterrupt:
        request_cancel()
        print("\nАнализ прерван пользователем.")
        return False

    line = "=" * 60
    print(line)
    print(f" СТАТИСТИКА: {path}")
    print(line)
    print(f" Файлов:  {files}")
    print(f" Папок:   {dirs}")
    print(f" Размер:  {utils.format_size(total_bytes)}")

    print("\n Типы файлов (топ-10 по размеру):")
    top_types = sorted(
        types.items(), key=lambda kv: kv[1]["total_size"], reverse=True
    )[:10]
    for ext, data in top_types:
        print(
            f"  {ext:<18}{data['count']:>8} шт."
            f"{utils.format_size(data['total_size']):>14}"
        )

    print("\n Атрибуты:")
    print(f"  Скрытых:       {attrs['hidden']}")
    print(f"  Системных:     {attrs['system']}")
    print(f"  Только чтение: {attrs['readonly']}")

    print("\n Крупнейшие файлы:")
    for size, full in largest:
        print(f"  {utils.format_size(size):>10}  {full}")
    print(line)
    return True


# ==========================================================================
# ЭТАП II. Задание 1: дубликаты файлов
# ==========================================================================
_HASH_CACHE: Dict[Tuple[str, int, float, str], str] = {}


def _default_checksum(file_path: str) -> str:
    """SHA-256 файла; читаем блоками, чтобы не грузить память."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as file:
        for block in iter(lambda: file.read(HASH_BLOCK_SIZE), b""):
            sha.update(block)
    return sha.hexdigest()


def _cached_checksum(
    file_path: str, size: int, func: Callable[[str], str]
) -> str:
    """Мемоизация хеша: ключ включает размер и время изменения."""
    mtime = os.stat(file_path).st_mtime
    key = (_norm(file_path), size, mtime, getattr(func, "__name__", "f"))
    if key not in _HASH_CACHE:
        _HASH_CACHE[key] = func(file_path)
    return _HASH_CACHE[key]


def find_duplicate_files_recursive(
    path: str,
    checksum_func: Optional[Callable[[str], str]] = None,
    visited: Optional[Set[str]] = None,
) -> Dict[str, List[str]]:
    """Поиск дубликатов: {hash: [path1, path2, ...]} (только группы > 1).

    Оптимизация: сначала группируем по размеру (у файлов разного размера
    дубликатов нет), хеш считаем только для совпавших размеров.
    """
    reset_cancel()
    checksum = checksum_func or _default_checksum
    seen: Set[str] = visited if visited is not None else set()

    by_size: Dict[int, List[str]] = defaultdict(list)
    for kind, full, item in _walk_entries(path):
        if kind != "file":
            continue
        key = _norm(full)
        if key in seen:
            continue
        seen.add(key)
        size = _item_size(full, item)
        if size > 0:
            by_size[size].append(full)

    groups: Dict[str, List[str]] = defaultdict(list)
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        for file_path in paths:
            if is_cancelled():
                break
            try:
                digest = _cached_checksum(file_path, size, checksum)
            except OSError:
                continue  # нет доступа или файл исчез
            groups[digest].append(file_path)
    return {h: p for h, p in groups.items() if len(p) > 1}


# ==========================================================================
# ЭТАП II. Задание 2: зависимости между файлами (#include)
# ==========================================================================
INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.MULTILINE)
DEFAULT_SOURCE_EXTS = [".c", ".cpp", ".cc", ".h", ".hpp"]


def _read_text(file_path: str) -> str:
    """Чтение текста: UTF-8, затем cp1251 (кодировки Windows)."""
    for encoding in ("utf-8", "cp1251"):
        try:
            with open(file_path, "r", encoding=encoding) as file:
                return file.read()
        except UnicodeDecodeError:
            continue
        except OSError:
            return ""
    return ""


def _canonical_cycle(cycle: List[str]) -> Tuple[str, ...]:
    """Один и тот же цикл с разным началом считаем одним."""
    start = cycle.index(min(cycle))
    return tuple(cycle[start:] + cycle[:start])


def _find_cycles(graph: Dict[str, List[str]]) -> List[List[str]]:
    """DFS с тремя состояниями: 0 не посещена, 1 в обработке, 2 готова."""
    state: Dict[str, int] = {}
    stack: List[str] = []
    cycles: List[List[str]] = []
    known: Set[Tuple[str, ...]] = set()

    def dfs(node: str, depth: int) -> None:
        state[node] = 1
        stack.append(node)
        for dep in graph.get(node, []):
            current = state.get(dep, 0)
            if current == 1:  # вернулись в вершину из текущего пути
                cycle = stack[stack.index(dep):]
                canon = _canonical_cycle(cycle)
                if canon not in known:
                    known.add(canon)
                    cycles.append(cycle + [dep])
            elif current == 0 and depth < DEFAULT_MAX_DEPTH:
                dfs(dep, depth + 1)
        stack.pop()
        state[node] = 2

    for node in list(graph):
        if state.get(node, 0) == 0:
            dfs(node, 0)
    return cycles


def _render_tree(
    graph: Dict[str, List[str]],
    node: str,
    prefix: str,
    on_path: List[str],
    lines: List[str],
    max_depth: int,
) -> None:
    """Рекурсивно рисует дерево зависимостей текстом."""
    deps = graph.get(node, [])
    for index, dep in enumerate(deps):
        last = index == len(deps) - 1
        branch = "└── " if last else "├── "
        mark = "  [ЦИКЛ]" if dep in on_path else ""
        lines.append(f"{prefix}{branch}{os.path.basename(dep)}{mark}")
        if not mark and len(on_path) < max_depth:
            extension = "    " if last else "│   "
            _render_tree(
                graph, dep, prefix + extension, on_path + [dep],
                lines, max_depth,
            )


def analyze_file_dependencies_recursive(
    root_path: str,
    target_extensions: Optional[List[str]] = None,
    dependency_tree: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Строит граф зависимостей #include "..." и ищет циклы.

    Возвращает словарь: tree, cycles, missing, files, visualization.
    """
    reset_cancel()
    exts = {
        e.lower() if e.startswith(".") else "." + e.lower()
        for e in (target_extensions or DEFAULT_SOURCE_EXTS)
    }
    graph: Dict[str, List[str]] = (
        dependency_tree if dependency_tree is not None else {}
    )

    sources: List[str] = []
    by_name: Dict[str, List[str]] = defaultdict(list)
    for kind, full, item in _walk_entries(root_path):
        if kind == "file" and os.path.splitext(full)[1].lower() in exts:
            sources.append(full)
            by_name[os.path.basename(full).lower()].append(full)

    missing: Dict[str, List[str]] = {}
    for source in sources:
        if is_cancelled():
            break
        deps: List[str] = []
        for include in INCLUDE_RE.findall(_read_text(source)):
            local = os.path.normpath(
                os.path.join(os.path.dirname(source), include)
            )
            if os.path.isfile(local):
                found = local
            else:
                options = by_name.get(os.path.basename(include).lower())
                found = options[0] if options else ""
            if found:
                if found not in deps:
                    deps.append(found)
            else:
                missing.setdefault(source, []).append(include)
        graph[source] = deps

    included = {d for deps in graph.values() for d in deps}
    roots = [s for s in sources if s not in included] or sources[:1]
    lines: List[str] = []
    for root in roots:
        lines.append(os.path.basename(root))
        _render_tree(graph, root, "", [root], lines, DEFAULT_MAX_DEPTH)

    return {
        "tree": graph,
        "cycles": _find_cycles(graph),
        "missing": missing,
        "files": len(sources),
        "visualization": "\n".join(lines),
    }


# ==========================================================================
# ЭТАП II. Задание 3: прогноз роста данных
# ==========================================================================
def _linear_slope(xs: List[float], ys: List[float]) -> float:
    """Наклон прямой по методу наименьших квадратов."""
    n = len(xs)
    if n < 2:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum(
        (x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)
    ) / denom


def _collect_growth(
    path: str,
    days_back: int,
    now: float,
    growth_data: Dict[str, List[int]],
    depth: int,
    visited: Set[str],
) -> List[int]:
    """Возвращает суммарные байты по дням для поддерева.

    Индекс 0 - самый старый день окна, последний индекс - сегодня.
    Результат каждого каталога складывается в growth_data[path].
    """
    buckets = [0] * (days_back + 1)
    key = _norm(path)
    if depth > DEFAULT_MAX_DEPTH or key in visited or is_cancelled():
        return buckets
    visited.add(key)

    ok, items = navigation.list_directory(path)
    if not ok:
        return buckets
    for item in items:
        full = os.path.join(path, str(item.get("name", "")))
        if _is_dir_item(item):
            if str(item.get("name", "")).lower() in SKIP_DIR_NAMES:
                continue
            if _is_link_or_junction(full):
                continue
            child = _collect_growth(
                full, days_back, now, growth_data, depth + 1, visited
            )
            buckets = [a + b for a, b in zip(buckets, child)]
        else:
            try:
                mtime = os.stat(full).st_mtime
            except OSError:
                continue
            age = int((now - mtime) // SECONDS_IN_DAY)
            if 0 <= age <= days_back:
                buckets[days_back - age] += _item_size(full, item)
    growth_data[path] = buckets
    return buckets


def predict_storage_growth_recursive(
    path: str,
    days_back: int = 30,
    growth_data: Optional[Dict[str, List[int]]] = None,
) -> Dict[str, float]:
    """Оценка роста {путь: МБ_в_день} для каталога и каждой подпапки.

    Берём файлы, изменённые за последние days_back дней, строим
    накопленный объём по дням и считаем наклон линейной регрессии.
    Результат отсортирован по убыванию ("горячие точки" роста сверху).
    Это оценка по датам изменения, а не точная история диска.
    """
    reset_cancel()
    data: Dict[str, List[int]] = (
        growth_data if growth_data is not None else {}
    )
    _collect_growth(path, days_back, time.time(), data, 0, set())

    rates: Dict[str, float] = {}
    for folder, buckets in data.items():
        total = 0
        cumulative: List[float] = []
        for day_bytes in buckets:
            total += day_bytes
            cumulative.append(total / (1024 * 1024))
        rates[folder] = _linear_slope(
            [float(i) for i in range(len(cumulative))], cumulative
        )
    return dict(sorted(rates.items(), key=lambda kv: kv[1], reverse=True))


def find_growth_hotspots(
    rates: Dict[str, float], threshold_mb_per_day: float = 1.0
) -> Dict[str, float]:
    """Каталоги, где рост выше порога (МБ в день)."""
    return {p: r for p, r in rates.items() if r >= threshold_mb_per_day}


# --------------------------------------------------------------------------
# Ручной запуск: python analysis.py [путь]
# --------------------------------------------------------------------------
if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    show_windows_directory_stats(target)

    print("\nДубликаты:")
    for digest, paths in find_duplicate_files_recursive(target).items():
        print(f" {digest[:12]}...")
        for item_path in paths:
            print(f"    {item_path}")

    print("\nРост данных (МБ/день, топ-5):")
    for folder, rate in list(
        predict_storage_growth_recursive(target).items()
    )[:5]:
        print(f" {rate:8.3f}  {folder}")

    deps = analyze_file_dependencies_recursive(target)
    print(f"\nИсходников: {deps['files']}, циклов: {len(deps['cycles'])}")
    if deps["visualization"]:
        print(deps["visualization"])