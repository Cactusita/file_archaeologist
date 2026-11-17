import os
import string
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import utils


def get_current_drive() -> str:
    """The current drive, for example 'C:'."""
    drive, _ = os.path.splitdrive(os.getcwd())
    return drive


def list_available_drives() -> List[str]:
    """Available drives: ['C:', 'D:', ...]."""
    drives = []
    for letter in string.ascii_uppercase:
        if os.path.exists(f"{letter}:\\"):
            drives.append(f"{letter}:")
    return drives


def is_root_path(path: str) -> bool:
    """True if the path is the root of a drive (the parent of the root is the root itself)."""
    return os.path.normpath(path) == utils.get_parent_path(path)


def list_directory(path: str) -> Tuple[bool, List[Dict[str, Any]]]:
    """Catalog contents: (True, items) or (False, [])."""
    is_valid, _ = utils.validate_windows_path(path)
    if not is_valid or not os.path.isdir(path):
        return False, []

    items: List[Dict[str, Any]] = []
    for name in utils.safe_windows_listdir(path):
        full_path = os.path.join(path, name)
        try:
            info = os.stat(full_path)
        except OSError:
            continue
        is_dir = os.path.isdir(full_path)
        attributes = utils.get_file_attributes(full_path)
        items.append({
            "name": name,
            "type": "directory" if is_dir else "file",
            "size": 0 if is_dir else info.st_size,
            "modified": datetime.fromtimestamp(
                info.st_mtime).strftime("%Y-%m-%d"),
            "hidden": utils.is_hidden_windows_file(full_path),
            "system": bool(attributes & utils.FILE_ATTRIBUTE_SYSTEM),
        })


    items.sort(key=lambda item: (item["type"] != "directory",
                                 item["name"].lower()))
    return True, items


def format_directory_output(items: List[Dict[str, Any]],
                            current_path: str = "") -> None:
    """Table of contents; at the root of the drive, it displays a list of drives."""
    if current_path and is_root_path(current_path):
        print("Диски: " + " ".join(list_available_drives()))
    if not items:
        print("(каталог пуст)")
        return

    print(f"{'Тип':<6}{'Имя':<40}{'Размер':>10}  {'Изменён':<11}Атр")
    dirs = 0 # счетчик папок
    for item in items:
        if item["type"] == "directory":
            kind = "<DIR>"
            size = ""
            dirs += 1
        else:
            kind = "FILE"
            size = utils.format_size(item["size"])
        attrs = "H" if item["hidden"] else "-"
        attrs += "S" if item["system"] else "-"
        name = item["name"]
        if len(name) > 38:
            name = name[:35] + "..."
        print(f"{kind:<6}{name:<40}{size:>10}  {item['modified']:<11}{attrs}")
    print(f"Папок: {dirs}, файлов: {len(items) - dirs}")
    print("Атр: H - скрытый, S - системный")


def move_up(current_path: str) -> str:
    """Parent directory; when at the root of the drive, we remain where we are."""
    parent = utils.get_parent_path(current_path)
    is_valid, _ = utils.validate_windows_path(parent)
    if is_valid:
        return parent
    return current_path


def move_down(current_path: str, target_dir: str) -> Tuple[bool, str]:
    """Switching to a subdirectory: (True, new path) or (False, current path)."""
    target = target_dir.strip()
    if not target:
        return False, current_path


    real_name = ""
    for name in utils.safe_windows_listdir(current_path):
        if name.lower() == target.lower():
            real_name = name
            break
    if not real_name:
        return False, current_path

    new_path = os.path.join(current_path, real_name)
    is_valid, _ = utils.validate_windows_path(new_path)
    if not is_valid or not os.path.isdir(new_path):
        return False, current_path
    return True, new_path


def get_windows_special_folders() -> Dict[str, str]:
    """Paths to the user's special folders (existing ones only)."""
    profile = os.environ.get("USERPROFILE", str(Path.home()))
    names = ("Desktop", "Documents", "Downloads",
             "Pictures", "Music", "Videos")
    folders = {"Home": profile}
    for name in names:
        folders[name] = os.path.join(profile, name)
    result = {}
    for name, path in folders.items():
        if os.path.isdir(path):
            result[name] = path
    return result
