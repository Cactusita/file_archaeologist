import fnmatch
import os
from typing import List, Dict, Any, Tuple

import analysis
import navigation
import utils

MAX_DEPTH = 50
MB = 1024 * 1024
SYSTEM_EXTENSIONS = [".exe", ".dll", ".sys"]
BAD_SYMBOLS = '/:"<>|'


def get_all_files(path: str,
                  depth: int = 0) -> List[Tuple[str, Dict[str, Any]]]:
    result = []
    if depth > MAX_DEPTH:
        return result

    ok, items = navigation.list_directory(path)
    if not ok:
        return result

    for item in items:
        full_path = os.path.join(path, item["name"])
        if item["type"] == "file":
            result.append((full_path, item))
        elif item["type"] == "directory":
            result.extend(get_all_files(full_path, depth + 1))
    return result


def get_extension(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def fix_extensions(extensions: List[str]) -> List[str]:
    result = []
    for ext in extensions:
        ext = ext.strip().lower()
        if ext == "":
            continue
        if not ext.startswith("."):
            ext = "." + ext
        if ext not in result:
            result.append(ext)
    return result


def get_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def is_inside(path: str, parent: str) -> bool:
    path = os.path.abspath(path).lower().rstrip("\\")
    parent = os.path.abspath(parent).lower().rstrip("\\")
    return path == parent or path.startswith(parent + "\\")


def get_system_directories() -> List[str]:
    windows_dir = os.environ.get("SystemRoot", "C:\\Windows")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)",
                                       "C:\\Program Files (x86)")
    result = []
    for folder in [windows_dir, program_files, program_files_x86]:
        if os.path.isdir(folder):
            result.append(folder)
    return result


def find_files_windows(pattern: str, path: str,
                       case_sensitive: bool = False,
                       show_progress: bool = False) -> List[str]:
    if pattern == "":
        return []
    if not case_sensitive:
        pattern = pattern.lower()

    total = 0
    if show_progress:
        ok, total = analysis.count_files(path)
        if not ok:
            total = 0

    found = []
    checked = 0
    for full_path, item in get_all_files(path):
        checked += 1
        name = item["name"]
        if not case_sensitive:
            name = name.lower()
        if fnmatch.fnmatchcase(name, pattern):
            found.append(full_path)
        if show_progress and checked % 200 == 0:
            print(f"\rПроверено файлов: {checked} из {total}", end="")

    if show_progress:
        print(f"\rПроверено файлов: {checked} из {total}")
    return found


def find_by_windows_extension(extensions: List[str], path: str,
                              use_analysis: bool = True) -> List[str]:
    wanted = fix_extensions(extensions)
    if len(wanted) == 0:
        return []

    if use_analysis:
        ok, stats = analysis.analyze_windows_file_types(path)
        if ok and stats:
            present = [str(key).lower() for key in stats]
            found_any = False
            for ext in wanted:
                if ext in present:
                    found_any = True
            if not found_any:
                return []

    found = []
    for full_path, item in get_all_files(path):
        if get_extension(item["name"]) in wanted:
            found.append(full_path)
    return found


def find_large_files_windows(min_size_mb: float,
                             path: str) -> List[Dict[str, Any]]:
    if min_size_mb < 0:
        return []

    ok, total_bytes = analysis.count_bytes(path)
    if ok and total_bytes < min_size_mb * MB:
        return []

    results = []
    for full_path, item in get_all_files(path):
        size = item["size"]
        if size >= min_size_mb * MB:
            results.append({
                "path": full_path,
                "size_mb": round(size / MB, 1),
                "type": get_extension(item["name"]),
            })

    results.sort(key=lambda x: x["size_mb"], reverse=True)
    return results


def find_windows_system_files(path: str) -> List[str]:
    roots = []
    for folder in get_system_directories():
        if is_inside(path, folder):
            roots.append(path)
        elif is_inside(folder, path):
            roots.append(folder)

    found = []
    for root in roots:
        for full_path, item in get_all_files(root):
            if get_extension(item["name"]) in SYSTEM_EXTENSIONS:
                found.append(full_path)
    return found


def print_attributes(paths: List[str]) -> None:
    try:
        folder = os.path.commonpath([os.path.dirname(p) for p in paths])
    except ValueError:
        return
    stats = analysis.get_windows_file_attributes_stats(folder)
    print(f"Атрибуты файлов в {folder}: {stats}")


def format_windows_search_results(results: List, search_type: str) -> None:
    if len(results) == 0:
        print("Ничего не найдено.")
        return

    total_bytes = 0
    print("-" * 70)

    match search_type:
        case "name" | "extension" | "system":
            print(f"Найдено файлов: {len(results)}")
            for file_path in results:
                size = get_size(file_path)
                total_bytes += size
                print(f"{utils.format_size(size):>10}  {file_path}")
            print_attributes(results)
        case "large":
            print(f"Найдено крупных файлов: {len(results)}")
            for entry in results:
                size = int(entry["size_mb"] * MB)
                total_bytes += size
                print(f"{utils.format_size(size):>10}  {entry['type']:<6} "
                      f"{entry['path']}")
            print_attributes([entry["path"] for entry in results])

    print("-" * 70)
    print("Общий размер найденного:", utils.format_size(total_bytes))


def search_menu_handler(current_path: str) -> bool:
    is_valid, error = utils.validate_windows_path(current_path)
    if not is_valid:
        print("Некорректный путь:", error)
        return False

    print(f"\n=== ПОИСК в {current_path} ===")
    print("1. По маске имени (*, ?)")
    print("2. По расширениям")
    print("3. Крупные файлы")
    print("4. Системные файлы Windows (.exe, .dll, .sys)")
    print("0. Выход")
    choice = input("Выберите пункт: ").strip()

    match choice:
        case "1":
            pattern = input("Маска (например, *.txt): ").strip()
            if pattern == "":
                print("Маска не задана.")
                return True
            for symbol in BAD_SYMBOLS:
                if symbol in pattern:
                    print("В маске нельзя использовать:", BAD_SYMBOLS)
                    return True
            results = find_files_windows(pattern, current_path,
                                         show_progress=True)
            format_windows_search_results(results, "name")
        case "2":
            text = input("Расширения через запятую (exe, dll): ")
            extensions = text.split(",")
            results = find_by_windows_extension(extensions, current_path)
            format_windows_search_results(results, "extension")
        case "3":
            text = input("Минимальный размер в МБ: ").replace(",", ".")
            try:
                min_size = float(text)
            except ValueError:
                print("Нужно ввести число, например 100 или 12.5")
                return True
            results = find_large_files_windows(min_size, current_path)
            format_windows_search_results(results, "large")
        case "4":
            results = find_windows_system_files(current_path)
            format_windows_search_results(results, "system")
        case "0":
            return False
        case _:
            print("Такого пункта нет.")
    return True