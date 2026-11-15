import os
import platform
from pathlib import Path
from typing import List, Tuple, Union

PathString = Union[str, Path] #Внутри PathString нет никаких данных. Это только подсказка для читателя и для редактора кода: функция принимает и строку, и Path. Вместо path: PathString можно было бы каждый раз писать длинное path: Union[str, Path], а так короче. Требует этого ТЗ: у каждой функции в шаблоне стоит PathString.

FORBIDDEN_CHARS = '/:*?"<>|' # запрещенные символы
MAX_PATH = 260 # максимальная длина пути

FILE_ATTRIBUTE_HIDDEN = 0x02 # 0x02 = 000010  скрытый
FILE_ATTRIBUTE_SYSTEM = 0x04 # 0x04 = 000100  системный



def is_windows_os() -> bool:
    """Проверка что программа запущена на Windows."""
    return platform.system() == "Windows"
    # возвращает bool, 0 если не Windows, 1 если Windows

def _add_long_prefix(path: str) -> str:
    """Добавляет \\\\?\\ к путям от 260 символов (UNC: \\\\?\\UNC\\)."""
    prefix = "\\\\?\\" #\\ в питоне это \
    if path.startswith(prefix) or not is_windows_os(): # если уже есть или не Windows
        return path                                    # то вернем в первозданном виде мабой
    full = os.path.abspath(path) # пример при текущей папке C:\work: a\b даёт C:\work\a\b, также убирает перемещение на одном уровне
    if len(full) < MAX_PATH: # если не больше 260, то его  вернем
        return full
    if full.startswith("\\\\"):  # сетевой путь \\server\share
        return prefix + "UNC\\" + full[2:] # результат: \\?\UNC\server\share\dir
    return prefix + full #возвращает префикс с путем


def _split_prefix(path: str) -> Tuple[str, str]:
    """Отделяет префикс длинного пути: (префикс, остаток)."""
    for prefix in ("\\\\?\\UNC\\", "\\\\?\\"): # перебираем префикс
        if path.startswith(prefix):            # если путь начинается с такого префикса, то
            return prefix, path[len(prefix):]  # отдельно кортежом вернем префикс и сам путь
    return "", path                            # но префикса может не быть


def validate_windows_path(path: PathString) -> Tuple[bool, str]:
    """Проверка пути: символы, длина, существование."""
    path_str = str(path)
    if not path_str.strip(): # если ничего не осталось после очистки strip()
        return False, "Пустой путь" # вернем False

    prefix, body = _split_prefix(path_str) # отделяем префикс при помощи вспомогательной функции
    if not prefix and len(path_str) > MAX_PATH: # если при отсутствии префикса больше 260 символов
        return False, f"Путь длиннее {MAX_PATH} символов" # вернем False

    _, tail = os.path.splitdrive(body)  # двоеточие диска не проверяем, Делит путь на диск и остаток. Диск нам не нужен, поэтому он записывается в _ (имя «выбрасываемой» переменной).
    bad_chars = sorted({char for char in tail if char in FORBIDDEN_CHARS}) #сортируем множество из запр символов
    if bad_chars: # если оно непустое
        return False, f"Запрещённые символы: {' '.join(bad_chars)}" # вернем False, покажем что нельзя

    if not os.path.exists(_add_long_prefix(path_str)): # os.path.exists(...) проверяет, есть ли такой путь на диске, если пути нет, то
        return False, "Путь не существует"                                                                                       # напишем это
    return True, "" # пройдя все эти проверки и не попав в False, вернем True и пустой текст ошибки


def format_size(size_bytes: int) -> str:
    """Форматирование размера: 1024 -> '1.0 KB', 1500000 -> '1.4 MB'."""
    size = float(size_bytes) # чтобы деление было дробным
    for unit in ("B", "KB", "MB", "GB"): # перебираем единицы измерения
        if size < 1024:
            if unit == "B": # если в байтах
                return f"{size:.0f} B" # то так и вернем ответ
            else:
                return f"{size:.1f} {unit}" # если нет, то будем до знака после запятой округлять
        size = size / 1024 # перед переходом к началу цикла
    return f"{size:.1f} TB" # если другие единицы не подходят


def get_parent_path(path: PathString) -> str:
    """Родитель каталога: C:\\ -> C:\\, C:\\Users -> C:\\."""
    norm = os.path.normpath(str(path)) # normpath наводит порядок: убирает лишние слеши и ...
    drive, tail = os.path.splitdrive(norm) # делит путь на диск и остаток.
    if drive and tail in ("", "\\"): # drive непустой (диск есть) и tail пустой либо равен \. Значит, мы в корне. C:\ истинно, C: истинно, C:\Users ложно.
        return drive + "\\"         # корень всегда возвращается в одном виде: C:\.
    return os.path.dirname(norm) or norm #C:\Users\Admin даёт C:\Users
                                         # or norm срабатывает, если dirname вернул пустую строку: у пути Users без диска родителя нет, возвращается Users.

def safe_windows_listdir(path: PathString) -> List[str]:
    """Содержимое каталога; при любой ошибке - пустой список."""
    try:
        return os.listdir(_add_long_prefix(str(path))) # os.listdir(...) читает каталог и возвращает имена внутри, без полного пути.
    except PermissionError:  # отказано в доступе
        return []
    except FileNotFoundError:  # каталога нет
        return []
    except OSError:  # длинные пути и прочие ошибки Windows
        return []


def get_file_attributes(path: PathString) -> int:
    """Маска атрибутов Windows (0 при ошибке)."""
    try:
        info = os.lstat(_add_long_prefix(str(path))) #str(path) превращает Path в строку. Path("C:/a") даёт "C:\a, os.lstat(...) запрашивает у Windows сведения о файле: размер, даты, атрибуты. Результат кладётся в info.
    except OSError: # срабатывает, если файла нет, нет доступа, путь слишком длинный и так далее. Все эти ошибки наследуют OSError.
        return 0
    return getattr(info, "st_file_attributes", 0) # st_file_attributes это поле внутри info с числом-маской. Оно есть только на Windows.
                                                  # getattr(объект, "имя", значение_по_умолчанию) берёт поле по имени. Если его нет (например, на Linux), вернёт 0, а не упадёт.


def is_hidden_windows_file(path: PathString) -> bool:
    """Есть ли у файла атрибут FILE_ATTRIBUTE_HIDDEN."""
    return bool(get_file_attributes(path) & FILE_ATTRIBUTE_HIDDEN) # & побитовое «и». Оно оставляет только те биты, которые стоят в обоих числах.


'''
os
Работа с операционной системой и файлами. Мы берём из неё:

os.listdir(путь): имена внутри каталога.
os.lstat(путь): сведения о файле, включая атрибуты Windows.
os.path.exists(путь): есть ли такой путь.
os.path.normpath, splitdrive, dirname, abspath: разбор и очистка путей.

platform
Узнаёт, на какой системе запущена программа. platform.system() возвращает "Windows", "Linux" или "Darwin" (macOS). Нужна в is_windows_os.

pathlib (берём Path)
Объект-путь. Path("C:/Users") хранит путь как объект, а не как строку. Нам нужен только как тип: функции должны принимать и строку, и Path.

typing (берём List, Tuple, Union)
Подсказки типов. На выполнение программы они не влияют, но показывают, что принимает и возвращает функция:

List[str]: список строк.
Tuple[bool, str]: пара из значения bool и строки.
Union[str, Path]: строка или Path.

Из них только os и platform что-то делают в работе программы, а pathlib и typing нужны для типов.
'''