"""Модуль поиска в Windows файловой системе (I этап)."""

import fnmatch
import os

import analysis
import navigation
import utils

MAX_DEPTH = 50  # максимальная глубина вложенности папок
MB = 1024 * 1024  # байт в одном мегабайте
SYSTEM_EXTENSIONS = [".exe", ".dll", ".sys"]
BAD_SYMBOLS = '/:"<>|'  # запрещённые символы (кроме * и ?)
FOLDER_TYPES = ["directory", "dir"]


# ---------- Вспомогательные функции ----------

def is_link(path: str) -> bool:
    """Проверка: ссылка (symlink или junction) или нет."""
    if os.path.islink(path):
        return True
    if hasattr(os.path, "isjunction"):  # есть только в Python 3.12+
        return os.path.isjunction(path)
    return False


def get_all_files(path: str, depth: int = 0) -> list:
    """Рекурсивно собирает все файлы в папке и её подпапках.

    Возвращает список пар (полный_путь, словарь_с_информацией).
    """
    result = []
    if depth > MAX_DEPTH:  # защита от слишком глубокой рекурсии
        return result

    ok, items = navigation.list_directory(path)
    if not ok:  # нет доступа к папке, пропускаем
        return result

    for item in items:
        full_path = os.path.join(path, item["name"])
        if item["type"] == "file":
            result.append((full_path, item))
        elif item["type"] in FOLDER_TYPES and not is_link(full_path):
            # рекурсия: заходим в подпапку
            result.extend(get_all_files(full_path, depth + 1))
    return result


def get_extension(name: str) -> str:
    """Расширение файла маленькими буквами: 'Doc.TXT' -> '.txt'."""
    return os.path.splitext(name)[1].lower()


def fix_extensions(extensions: list) -> list:
    """Приводит расширения к виду '.exe' (точка + маленькие буквы)."""
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
    """Размер файла в байтах (0, если не удалось узнать)."""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def is_inside(path: str, parent: str) -> bool:
    """Проверка: лежит ли path внутри папки parent (регистр не важен)."""
    path = os.path.abspath(path).lower().rstrip("\\")
    parent = os.path.abspath(parent).lower().rstrip("\\")
    return path == parent or path.startswith(parent + "\\")


def get_system_directories() -> list:
    """Системные папки Windows, которые есть на этом компьютере."""
    windows_dir = os.environ.get("SystemRoot", "C:\\Windows")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)",
                                       "C:\\Program Files (x86)")
    result = []
    for folder in [windows_dir, program_files, program_files_x86]:
        if os.path.isdir(folder):
            result.append(folder)
    return result


# ---------- Функции поиска ----------

def find_files_windows(pattern: str, path: str,
                       case_sensitive: bool = False,
                       show_progress: bool = False) -> list:
    """Поиск файлов по маске (* и ?) во всех подпапках."""
    if pattern == "":
        return []
    if not case_sensitive:
        pattern = pattern.lower()

    # общее количество файлов нужно только для вывода прогресса
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


def find_by_windows_extension(extensions: list, path: str,
                              use_analysis: bool = True) -> list:
    """Поиск файлов по списку расширений, например ['exe', '.dll'].

    use_analysis: сначала смотрим статистику из analysis, и если нужных
    расширений там нет, то обход папок не делаем. Если аналитик считает
    статистику не рекурсивно, то поставить False.
    """
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


def find_large_files_windows(min_size_mb: float, path: str) -> list:
    """Поиск файлов размером не меньше min_size_mb мегабайт."""
    if min_size_mb < 0:
        return []

    # если вся папка меньше порога, то крупных файлов в ней точно нет
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

    # самые большие файлы - в начале списка
    results.sort(key=lambda x: x["size_mb"], reverse=True)
    return results


def find_windows_system_files(path: str) -> list:
    """Поиск .exe, .dll, .sys в системных папках Windows.

    Ищем только там, где системные папки пересекаются с path:
    - path внутри системной папки: ищем в path;
    - системная папка внутри path (например, path = C:\\): ищем в ней.
    """
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


# ---------- Вывод результатов ----------

def print_attributes(paths: list) -> None:
    """Печатает статистику атрибутов для общей папки найденных файлов."""
    try:
        folder = os.path.commonpath([os.path.dirname(p) for p in paths])
    except ValueError:  # файлы на разных дисках
        return
    stats = analysis.get_windows_file_attributes_stats(folder)
    print(f"Атрибуты файлов в {folder}: {stats}")


def format_windows_search_results(results: list, search_type: str) -> None:
    """Красивый вывод результатов.

    search_type: 'name', 'extension', 'system' - список путей,
                 'large' - список словарей.
    """
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
        case _:
            print("Неизвестный тип поиска:", search_type)
            return

    print("-" * 70)
    print("Общий размер найденного:", utils.format_size(total_bytes))


# ---------- Меню ----------

def search_menu_handler(current_path: str) -> bool:
    """Меню поиска. Возвращает True, чтобы продолжить, False - выход."""
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