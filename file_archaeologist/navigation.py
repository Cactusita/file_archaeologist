import os
import string
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import utils


def get_current_drive() -> str:
    """Текущий диск, например 'C:'."""
    drive, _ = os.path.splitdrive(os.getcwd()) # getcwd возвращает текущую рабочую папку, splitdrive делит на диск и остаток, остаток не нужен
    return drive # возвращает диск


def list_available_drives() -> List[str]:
    """Доступные диски: ['C:', 'D:', ...]."""
    drives = [] # список куда будем складывать диски
    for letter in string.ascii_uppercase: # string.ascii_uppercase это строка "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if os.path.exists(f"{letter}:\\"): # проверяем если есть такой путь(с такой буквой)
            drives.append(f"{letter}:")    # есть - добавляем
    return drives # вернем список этот


def is_root_path(path: str) -> bool:
    """True, если путь - корень диска (родитель корня он сам)."""
    return os.path.normpath(path) == utils.get_parent_path(path) # слева приводим путь к нормальному виду, справ родительский каталог, для диска это он C:\


def list_directory(path: str) -> Tuple[bool, List[Dict[str, Any]]]:
    """Содержимое каталога: (True, элементы) или (False, [])."""
    is_valid, _ = utils.validate_windows_path(path) # проверяет путь на валидность, код ошибки в _
    if not is_valid or not os.path.isdir(path): # если путь некорректен или это не папка (например, файл), возвращаем неудачу и пустой список
        return False, [] # вернем False и пустой список

    items: List[Dict[str, Any]] = [] # пустой список, куда будем складывать словари. Запись после двоеточия только подсказка типа
    for name in utils.safe_windows_listdir(path): # перебираем имена в каталоге
        full_path = os.path.join(path, name) # склеиваем путь каталога с именем
        try:
            info = os.stat(full_path) # os.stat запрашивает у Windows сведения об элементе: размер, дату изменения
        except OSError:
            continue  # нет доступа к элементу - пропускаем
        is_dir = os.path.isdir(full_path) # True, если это папка, нужно для типа и размеров
        attributes = utils.get_file_attributes(full_path) # число маска аттрибутов Windows
        items.append({                # добавляет в список 1 словарь с 6 значениями
            "name": name,             # имя
            "type": "directory" if is_dir else "file",  #тип папка\файл
            "size": 0 if is_dir else info.st_size,  # если папка, то размер 0, если файл, то вбайтах размер
            "modified": datetime.fromtimestamp( # info.st_mtime время изменения числом (секунды с 1970 года)
                info.st_mtime).strftime("%Y-%m-%d"), # datetime.fromtimestamp(...) превращает его в дату и время, strftime приводим год-месяц-день
            "hidden": utils.is_hidden_windows_file(full_path), # True если файл скрытый
            "system": bool(attributes & utils.FILE_ATTRIBUTE_SYSTEM), # True, если системный
        })

    # сначала папки, потом файлы; внутри групп - по имени без регистра
    items.sort(key=lambda item: (item["type"] != "directory",     # lambda item: ... короткая функция без имени. Для каждого элемента она возвращает ключ сортировки, Ключ это пара из двух значений. Python сравнивает по первому, при равенстве по второму.
                                 item["name"].lower())) # item["type"] != "directory" для папки False (то есть 0), для файла True (1). Значит, папки идут первыми. item["name"].lower() имя строчными буквами: внутри группы порядок по алфавиту без учёта регистра. MixedCase встанет между media и programs, как в твоём выводе.
    return True, items # успех и готовый список


def format_directory_output(items: List[Dict[str, Any]],
                            current_path: str = "") -> None: # результат работы kist_directory и по умолчвнию пустая строка, возвращаеем None
    """Таблица содержимого; в корне диска показывает список дисков."""
    if current_path and is_root_path(current_path): # Если путь передан и это корень диска, то выполняется следующая строка. Пустая строка считается ложью.
        print("Диски: " + " ".join(list_available_drives())) # Печатается строка Диски: C: D: при помощи соединения join
    if not items: # если нет ничего
        print("(каталог пуст)") # пишем что каталог пуст
        return # завершаем

    print(f"{'Тип':<6}{'Имя':<40}{'Размер':>10}  {'Изменён':<11}Атр") # < выровнять по левому краю, > по правому
    dirs = 0 # счетчик папок
    for item in items: # перебирает словари по одному
        if item["type"] == "directory":
            kind = "<DIR>"
            size = ""     #Для папки: kind = "<DIR>", size = "" (у папки размер не показываем), dirs += 1 (счётчик плюс один).
            dirs += 1
        else:
            kind = "FILE"
            size = utils.format_size(item["size"]) # Для файла: kind = "FILE", size = utils.format_size(item["size"]). Например, 20480 превращается в 20.0 KB
        attrs = "H" if item["hidden"] else "-" # H, если скрытый
        attrs += "S" if item["system"] else "-" #S, если системный добавлением в строку через +=, Итог: --, H- или HS
        name = item["name"]
        if len(name) > 38:
            name = name[:35] + "..." #длинное имя обрезаем до 35 и добавляем троеточие
        print(f"{kind:<6}{name:<40}{size:>10}  {item['modified']:<11}{attrs}") # печатает строку такую же по формату как в заголовке
    print(f"Папок: {dirs}, файлов: {len(items) - dirs}") # Всего элементов минус папки равно числу файлов.
    print("Атр: H - скрытый, S - системный") # для пользователя объясним что такое h и что такое S


def move_up(current_path: str) -> str:
    """Родительский каталог; в корне диска остаёмся на месте."""
    parent = utils.get_parent_path(current_path) # возвращает родительский каталог
    is_valid, _ = utils.validate_windows_path(parent) # проверяет родителя и возвращает True\False
    if is_valid: # если True
        return parent # возвращаем родительский каталог
    return current_path # остаемся где были


def move_down(current_path: str, target_dir: str) -> Tuple[bool, str]:
    """Переход в подкаталог: (True, новый путь) или (False, текущий)."""
    target = target_dir.strip() # удаляет ненужные пробелы по бокам
    if not target: # если ничего не осталось
        return False, current_path # вернем False, остаемся там же где и были

    # Windows не различает регистр: ищем имя без его учёта
    real_name = "" # сюда запишем настоящее имя папки
    for name in utils.safe_windows_listdir(current_path): # берём список имён внутри текущей папки и перебираем по одному. name это имя очередного элемента
        if name.lower() == target.lower(): # сравниваем без учета регистра(так видит Windows)
            real_name = name # записываем в нужном регистре
            break # выходим из цикла, если нашли
    if not real_name: # если нет такого
        return False, current_path # False и текущее место

    new_path = os.path.join(current_path, real_name) # склеивает путь с нужным разделителем
    is_valid, _ = utils.validate_windows_path(new_path) # проверяем путь на валидность
    if not is_valid or not os.path.isdir(new_path): # пройдет проверку если путь валиден или это не папка
        return False, current_path # вернем False и текущий путь
    return True, new_path # вернем True и новый путь если все хорошо


def get_windows_special_folders() -> Dict[str, str]:
    """Пути к специальным папкам пользователя (только существующие)."""
    profile = os.environ.get("USERPROFILE", str(Path.home())) # os.environ словарь переменных окружения Windows. В нём есть USERPROFILE, это путь к твоей домашней папке, например C:\Users\OE
    names = ("Desktop", "Documents", "Downloads",
             "Pictures", "Music", "Videos") # стандартные подпапки профиля
    folders = {"Home": profile} # создаёт словарь с одной записью: ключ "Home", значение путь к профилю.
    for name in names: # перебирает названия
        folders[name] = os.path.join(profile, name) # добавляет в словарь путь, где мы присоединяем имя папки
    result = {} # итоговый словарь
    for name, path in folders.items(): # пара имени и пути
        if os.path.isdir(path): # только если папка существует
            result[name] = path #по ключу имени значением будет путь
    return result
