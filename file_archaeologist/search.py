"""Модуль поиска в Windows файловой системе (I этап).

Зависимости: utils.py, navigation.py, analysis.py.

Контракт, который ожидается от навигации: navigation.list_directory(path)
возвращает (True, [{'name': ..., 'type': 'file' | 'directory',
'size': int, 'modified': str, 'hidden': bool}, ...]) или (False, []).
"""

import fnmatch
import os
from typing import Any, Dict, Iterator, List, Optional, Tuple

import analysis
import navigation
import utils

FILE_TYPES = {"file"}
DIR_TYPES = {"directory", "dir"}
SYSTEM_EXTENSIONS = {".exe", ".dll", ".sys"}
MAX_SEARCH_DEPTH = 50
BYTES_IN_MB = 1024 * 1024
PROGRESS_STEP = 200
FORBIDDEN_IN_PATTERN = '/:"<>|'


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _is_link(path: str) -> bool:
    """Символическая ссылка или junction point (их обходить нельзя)."""
    if os.path.islink(path):
        return True
    isjunction = getattr(os.path, "isjunction", None)  # Python 3.12+
    return bool(isjunction and isjunction(path))


def _walk_tree(path: str,
               max_depth: int = MAX_SEARCH_DEPTH,
               depth: int = 0,
               visited: Optional[set] = None
               ) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """Рекурсивный обход каталога, общий для всех функций поиска.

    Отдаёт пары (полный_путь, словарь_элемента) для файлов и папок.
    Защищает от циклов (visited), от бесконечной глубины (max_depth),
    пропускает symlink/junction и недоступные каталоги.
    """
    if depth > max_depth:
        return
    if visited is None:
        visited = set()
    try:
        real = os.path.normcase(os.path.realpath(path))
    except OSError:
        return
    if real in visited:
        return
    visited.add(real)

    ok, items = navigation.list_directory(path)
    if not ok:
        return

    for item in items:
        full_path = os.path.join(path, item["name"])
        yield full_path, item
        if item.get("type") in DIR_TYPES and not _is_link(full_path):
            yield from _walk_tree(full_path, max_depth, depth + 1, visited)


def _get_extension(name: str) -> str:
    """Расширение имени файла в нижнем регистре, например '.exe'."""
    return os.path.splitext(name)[1].lower()


def _normalize_extensions(extensions: List[str]) -> List[str]:
    """Добавляет точку, убирает пробелы, приводит к нижнему регистру."""
    result: List[str] = []
    for ext in extensions:
        ext = ext.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        if ext not in result:
            result.append(ext)
    return result


def _safe_size(path: str) -> int:
    """Размер файла или 0, если он недоступен."""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _is_inside(path: str, parent: str) -> bool:
    """Лежит ли path внутри parent (или совпадает с ним), без учёта регистра."""
    try:
        path_n = os.path.normcase(os.path.abspath(path))
        parent_n = os.path.normcase(os.path.abspath(parent))
        return os.path.commonpath([path_n, parent_n]) == parent_n
    except ValueError:  # разные диски
        return False


def _get_system_directories() -> List[str]:
    """Системные каталоги Windows, существующие на этой машине."""
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidates = [
        system_root,
        os.path.join(system_root, "System32"),
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ]
    result: List[str] = []
    for candidate in candidates:
        if os.path.isdir(candidate) and candidate not in result:
            result.append(candidate)
    return result


# ---------------------------------------------------------------------------
# Функции поиска
# ---------------------------------------------------------------------------

def find_files_windows(pattern: str,
                       path: str,
                       case_sensitive: bool = False,
                       show_progress: bool = False) -> List[str]:
    """Поиск файлов по маске Windows (* и ?) во всём дереве каталога."""
    if not pattern:
        return []
    if not case_sensitive:
        pattern = pattern.lower()

    total = 0
    if show_progress:
        ok, total = analysis.count_files(path)
        if not ok:
            total = 0

    found: List[str] = []
    checked = 0
    for full_path, item in _walk_tree(path):
        if item.get("type") not in FILE_TYPES:
            continue
        checked += 1
        name = item["name"] if case_sensitive else item["name"].lower()
        if fnmatch.fnmatchcase(name, pattern):
            found.append(full_path)
        if show_progress and checked % PROGRESS_STEP == 0:
            print(f"\rПроверено файлов: {checked} из {total}",
                  end="", flush=True)
    if show_progress:
        print(f"\rПроверено файлов: {checked} из {total}")
    return found


def find_by_windows_extension(extensions: List[str],
                              path: str,
                              use_analysis: bool = True) -> List[str]:
    """Поиск файлов по списку расширений ('exe', '.DLL' и т.п.).

    use_analysis: предварительная проверка через
    analysis.analyze_windows_file_types(). Если статистика по каталогу не
    содержит ни одного из нужных расширений, обход не запускается.
    Предполагается, что аналитик считает статистику рекурсивно; если это
    не так, поставьте use_analysis=False.
    """
    wanted = set(_normalize_extensions(extensions))
    if not wanted:
        return []

    if use_analysis:
        ok, stats = analysis.analyze_windows_file_types(path)
        if ok and stats:
            present = {str(key).lower() for key in stats}
            if not wanted & present:
                return []

    return [
        full_path
        for full_path, item in _walk_tree(path)
        if item.get("type") in FILE_TYPES
        and _get_extension(item["name"]) in wanted
    ]


def find_large_files_windows(min_size_mb: float,
                             path: str) -> List[Dict[str, Any]]:
    """Поиск файлов не меньше min_size_mb МБ, по убыванию размера."""
    if min_size_mb < 0:
        return []

    # Быстрая отсечка: если весь каталог меньше порога, крупных файлов нет.
    ok, total_bytes = analysis.count_bytes(path)
    if ok and total_bytes < min_size_mb * BYTES_IN_MB:
        return []

    results: List[Dict[str, Any]] = []
    for full_path, item in _walk_tree(path):
        if item.get("type") not in FILE_TYPES:
            continue
        size = item.get("size", 0)
        if size >= min_size_mb * BYTES_IN_MB:
            results.append({
                "path": full_path,
                "size_mb": round(size / BYTES_IN_MB, 1),
                "type": _get_extension(item["name"]),
            })
    results.sort(key=lambda entry: entry["size_mb"], reverse=True)
    return results


def find_windows_system_files(path: str) -> List[str]:
    """Поиск .exe, .dll, .sys в системных каталогах Windows.

    Ищет только там, где системные каталоги пересекаются с path:
    - path внутри системного каталога -> ищем в path;
    - системный каталог внутри path (например, path = C:\\) -> ищем в нём.
    """
    roots: List[str] = []
    for system_dir in _get_system_directories():
        if _is_inside(path, system_dir):
            roots.append(path)
        elif _is_inside(system_dir, path):
            roots.append(system_dir)

    # Убираем корни, вложенные в другие корни, чтобы не искать дважды.
    unique_roots = [
        root for root in dict.fromkeys(roots)
        if not any(other != root and _is_inside(root, other)
                   for other in roots)
    ]

    found: List[str] = []
    seen = set()
    for root in unique_roots:
        for full_path, item in _walk_tree(root):
            if item.get("type") not in FILE_TYPES:
                continue
            if _get_extension(item["name"]) not in SYSTEM_EXTENSIONS:
                continue
            key = os.path.normcase(full_path)
            if key not in seen:
                seen.add(key)
                found.append(full_path)
    return found


# ---------------------------------------------------------------------------
# Вывод результатов
# ---------------------------------------------------------------------------

def _print_attributes_stats(paths: List[str]) -> None:
    """Статистика атрибутов в общем каталоге найденных файлов."""
    try:
        common = os.path.commonpath([os.path.dirname(p) for p in paths])
    except ValueError:
        return
    if not os.path.isdir(common):
        return
    try:
        stats = analysis.get_windows_file_attributes_stats(common)
    except OSError:
        return
    if stats:
        parts = ", ".join(f"{name}: {count}" for name, count in stats.items())
        print(f"\nАтрибуты файлов в {common}: {parts}")


def format_windows_search_results(results: List,
                                  search_type: str) -> None:
    """Вывод результатов поиска.

    search_type: 'name', 'extension', 'system' (список путей)
    или 'large' (список словарей из find_large_files_windows).
    """
    if not results:
        print("Ничего не найдено.")
        return

    match search_type:
        case "name" | "extension" | "system":
            print(f"\nНайдено файлов: {len(results)}")
            print("-" * 70)
            for file_path in results:
                size = utils.format_size(_safe_size(file_path))
                print(f"{size:>10}  {file_path}")
            _print_attributes_stats(results)
        case "large":
            print(f"\nНайдено крупных файлов: {len(results)}")
            print("-" * 70)
            print(f"{'Размер':>10}  {'Тип':<8} Путь")
            for entry in results:
                size = utils.format_size(int(entry["size_mb"] * BYTES_IN_MB))
                ext = entry["type"] or "-"
                print(f"{size:>10}  {ext:<8} {entry['path']}")
            _print_attributes_stats([entry["path"] for entry in results])
        case _:
            print(f"Неизвестный тип поиска: {search_type}")
            return

    # Сводка: общий размер найденного.
    if search_type == "large":
        total = sum(int(entry["size_mb"] * BYTES_IN_MB) for entry in results)
    else:
        total = sum(_safe_size(file_path) for file_path in results)
    print("-" * 70)
    print(f"Общий размер найденного: {utils.format_size(total)}")


# ---------------------------------------------------------------------------
# Меню
# ---------------------------------------------------------------------------

def _ask(prompt: str) -> Optional[str]:
    """input() с защитой от Ctrl+C / Ctrl+Z; None означает отмену."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def search_menu_handler(current_path: str) -> bool:
    """Интерактивное меню поиска. True - продолжить, False - выйти."""
    valid, error = utils.validate_windows_path(current_path)
    if not valid:
        print(f"Некорректный путь для поиска: {error}")
        return False

    print(f"\n=== ПОИСК в {current_path} ===")
    print("1. По маске имени (*, ?)")
    print("2. По расширениям")
    print("3. Крупные файлы")
    print("4. Системные файлы Windows (.exe, .dll, .sys)")
    print("0. Выход из поиска")

    choice = _ask("Выберите пункт: ")
    if choice is None:
        return False

    match choice:
        case "1":
            pattern = _ask("Маска (например, *.txt): ")
            if not pattern:
                print("Маска не задана.")
                return True
            if any(ch in pattern for ch in FORBIDDEN_IN_PATTERN):
                print(f"Маска содержит запрещённые символы: "
                      f"{FORBIDDEN_IN_PATTERN}")
                return True
            results = find_files_windows(pattern, current_path,
                                         show_progress=True)
            format_windows_search_results(results, "name")
        case "2":
            raw = _ask("Расширения через запятую (exe, .dll, msi): ")
            if not raw:
                print("Расширения не заданы.")
                return True
            extensions = [part for part in raw.replace(";", ",").split(",")]
            results = find_by_windows_extension(extensions, current_path)
            format_windows_search_results(results, "extension")
        case "3":
            raw = _ask("Минимальный размер в МБ: ")
            try:
                min_size = float((raw or "").replace(",", "."))
            except ValueError:
                print("Нужно ввести число, например 100 или 12.5.")
                return True
            results = find_large_files_windows(min_size, current_path)
            format_windows_search_results(results, "large")
        case "4":
            results = find_windows_system_files(current_path)
            format_windows_search_results(results, "system")
        case "0":
            return False
        case _:
            print("Неизвестный пункт меню.")
    return True