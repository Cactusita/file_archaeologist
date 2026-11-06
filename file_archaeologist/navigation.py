import fnmatch
import os
import string
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

import utils

# Системные каталоги, которые не обходим в дереве (для безопасности)
SKIP_DIRS = {"windows", "$recycle.bin", "system volume information",
             "config.msi", "recovery"}


# ---------------------------------------------------------------- I этап

def get_current_drive() -> str:
    """Текущий диск, например 'C:'."""
    drive, _ = os.path.splitdrive(os.getcwd())
    return drive


def list_available_drives() -> List[str]:
    """Доступные диски: ['C:', 'D:', ...]."""
    drives = []
    for letter in string.ascii_uppercase:
        if os.path.exists(f"{letter}:\\"):
            drives.append(f"{letter}:")
    return drives


def is_root_path(path: str) -> bool:
    """True, если путь - корень диска (у корня родитель он сам)."""
    return os.path.normpath(path) == utils.get_parent_path(path)


def is_reparse_point(path: str) -> bool:
    """Symlink или junction: в них не заходим, чтобы не зациклиться."""
    attrs = utils.get_file_attributes(path)
    return bool(attrs & utils.FILE_ATTRIBUTE_REPARSE_POINT) \
        or os.path.islink(path)


def list_directory(path: str) -> Tuple[bool, List[Dict[str, Any]]]:
    """Содержимое каталога: (True, элементы) или (False, [])."""
    is_valid, _ = utils.validate_windows_path(path)
    if not is_valid or not os.path.isdir(path):
        return False, []

    items: List[Dict[str, Any]] = []
    for name in utils.safe_windows_listdir(path):
        full_path = os.path.join(path, name)
        try:
            info = os.stat(full_path)
        except OSError:
            continue  # нет доступа к элементу - пропускаем
        is_dir = os.path.isdir(full_path)
        attrs = utils.get_file_attributes(full_path)
        items.append({
            "name": name,
            "type": "directory" if is_dir else "file",
            "size": 0 if is_dir else info.st_size,
            "modified": datetime.fromtimestamp(
                info.st_mtime).strftime("%Y-%m-%d"),
            "hidden": utils.is_hidden_windows_file(full_path),
            "system": bool(attrs & utils.FILE_ATTRIBUTE_SYSTEM),
        })
    # сначала папки, потом файлы, внутри - по имени без учёта регистра
    items.sort(key=lambda item: (item["type"] != "directory",
                                 item["name"].lower()))
    return True, items


def format_directory_output(items: List[Dict[str, Any]],
                            current_path: str = "") -> None:
    """Таблица содержимого; в корне диска показывает список дисков."""
    if current_path and is_root_path(current_path):
        print("Диски: " + " ".join(list_available_drives()))
    if not items:
        print("(каталог пуст)")
        return

    print(f"{'Тип':<6}{'Имя':<40}{'Размер':>10}  {'Изменён':<11}Атр")
    dirs = 0
    for item in items:
        if item["type"] == "directory":
            kind, size = "<DIR>", ""
            dirs += 1
        else:
            kind, size = "FILE", utils.format_size(item["size"])
        attrs = ("H" if item["hidden"] else "-") \
                + ("S" if item["system"] else "-")
        name = item["name"]
        if len(name) > 38:
            name = name[:35] + "..."
        print(f"{kind:<6}{name:<40}{size:>10}  {item['modified']:<11}{attrs}")
    print(f"Папок: {dirs}, файлов: {len(items) - dirs}")
    print("Атр: H - скрытый, S - системный")


def move_up(current_path: str) -> str:
    """Родительский каталог; в корне диска остаёмся на месте."""
    parent = utils.get_parent_path(current_path)
    is_valid, _ = utils.validate_windows_path(parent)
    if is_valid:
        return parent
    return current_path


def move_down(current_path: str, target_dir: str) -> Tuple[bool, str]:
    """Переход в подкаталог: (True, новый путь) или (False, текущий)."""
    target = target_dir.strip()
    if not target:
        return False, current_path

    # Windows не различает регистр: ищем имя без его учёта
    real_name: Optional[str] = None
    for name in utils.safe_windows_listdir(current_path):
        if name.lower() == target.lower():
            real_name = name
            break
    if real_name is None:
        return False, current_path

    new_path = os.path.join(current_path, real_name)
    is_valid, _ = utils.validate_windows_path(new_path)
    if not is_valid or not os.path.isdir(new_path):
        return False, current_path
    return True, new_path


def get_windows_special_folders() -> Dict[str, str]:
    """Пути к специальным папкам пользователя (только существующие)."""
    profile = os.environ.get("USERPROFILE", str(Path.home()))
    names = ("Desktop", "Documents", "Downloads",
             "Pictures", "Music", "Videos")
    folders = {"Home": profile}
    for name in names:
        folders[name] = os.path.join(profile, name)
    return {name: path for name, path in folders.items()
            if os.path.isdir(path)}


# --------------------------------------------------------------- II этап

def build_windows_tree_recursive(path: utils.PathString, depth: int = 0,
                                 max_depth: int = 5) -> Dict[str, Any]:
    """Дерево каталогов: {'name', 'type', 'children'}."""
    path_str = str(path)
    node: Dict[str, Any] = {
        "name": os.path.basename(path_str.rstrip("\\")) or path_str,
        "type": "directory" if os.path.isdir(path_str) else "file",
    }
    if node["type"] == "file":
        return node
    node["children"] = []
    if depth >= max_depth:  # база рекурсии: глубже не идём
        return node

    for name in sorted(utils.safe_windows_listdir(path_str), key=str.lower):
        full_path = os.path.join(path_str, name)
        if os.path.isdir(full_path):
            if name.lower() in SKIP_DIRS or is_reparse_point(full_path):
                continue
        node["children"].append(
            build_windows_tree_recursive(full_path, depth + 1, max_depth))
    return node


def format_tree(node: Dict[str, Any], prefix: str = "") -> List[str]:
    """Строки для печати дерева (├── и └──). Корень печатает вызывающий."""
    lines: List[str] = []
    children = node.get("children", [])
    for index, child in enumerate(children):
        is_last = index == len(children) - 1
        lines.append(prefix + ("└── " if is_last else "├── ")
                     + child["name"])
        lines.extend(format_tree(child, prefix + ("    " if is_last
                                                  else "│   ")))
    return lines


def recursive_path_explorer(
        start_path: str, history: Optional[List[str]] = None,
        visited: Optional[Set[str]] = None, depth: int = 0
) -> Generator[Tuple[str, List[str]], None, None]:
    """Обходит каталоги; yield (текущий путь, история от старта до него).

    История позволяет вернуться назад: history[-2] - предыдущий каталог.
    """
    if history is None:
        history = []
    if visited is None:
        visited = set()
    real_path = os.path.normcase(os.path.realpath(start_path))
    if real_path in visited or depth > utils.MAX_RECURSION_DEPTH:
        return  # уже были здесь (цикл) или слишком глубоко
    visited.add(real_path)

    current_history = history + [start_path]
    yield start_path, current_history

    for name in sorted(utils.safe_windows_listdir(start_path), key=str.lower):
        full_path = os.path.join(start_path, name)
        if os.path.isdir(full_path) and not is_reparse_point(full_path):
            yield from recursive_path_explorer(
                full_path, current_history, visited, depth + 1)


def _item_type(path: str, is_dir: bool) -> str:
    """SYS, HIDDEN, DIR или FILE (в таком порядке приоритета)."""
    attrs = utils.get_file_attributes(path)
    if attrs & utils.FILE_ATTRIBUTE_SYSTEM:
        return "SYS"
    if attrs & utils.FILE_ATTRIBUTE_HIDDEN:
        return "HIDDEN"
    return "DIR" if is_dir else "FILE"


def analyze_windows_structure_recursive(
        path: str, pattern: str = "*", level: int = 0
) -> List[Tuple[int, str, str]]:
    """Структура каталога: [(уровень, тип, путь), ...].

    Шаблон (например '*.exe') фильтрует файлы; папки показываются всегда.
    """
    result: List[Tuple[int, str, str]] = []
    if level > utils.MAX_RECURSION_DEPTH:
        return result

    is_dir = os.path.isdir(path)
    name = os.path.basename(path) or path
    if is_dir or fnmatch.fnmatch(name, pattern):
        result.append((level, _item_type(path, is_dir), path))

    if is_dir and not is_reparse_point(path):
        for child in sorted(utils.safe_windows_listdir(path), key=str.lower):
            result.extend(analyze_windows_structure_recursive(
                os.path.join(path, child), pattern, level + 1))
    return result