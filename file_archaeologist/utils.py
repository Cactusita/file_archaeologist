import os
import platform
from pathlib import Path
from typing import Union, List, Tuple
import ctypes

PathString = Union[str, Path]

def is_windows_os() -> bool:
    """Проверка что программа запущена на Windows"""
    return platform.system() == 'Windows'


def validate_windows_path(path: PathString) -> Tuple[bool, str]:
    """Проверка корректности Windows пути"""
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
    # TODO: Вернуть путь к родительскому каталогу
    # Учесть особенности: C:\ → C:\, C:\Users → C:\
    # Использовать os.path.dirname с учетом Windows
    pass

def safe_windows_listdir(path: PathString) -> List[str]:
    """Безопасное получение содержимого каталога в Windows"""
    # TODO: Вернуть список элементов каталога или пустой список при ошибке
    # Обрабатывать Windows-specific ошибки:
    # - PermissionError (отказ в доступе)
    # - FileNotFoundError
    # - OSError для длинных путей
    pass

def is_hidden_windows_file(path: PathString) -> bool:
    """Проверка является ли файл скрытым в Windows"""

    # TODO: Проверить атрибуты файла на наличие FILE_ATTRIBUTE_HIDDEN
    # Использовать os.stat или ctypes для проверки атрибутов Windows
    pass