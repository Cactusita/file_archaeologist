import os
import platform
import sys
from typing import NoReturn

import analysis
import navigation
import search
import utils

MENU = (
    "1 - Показать содержимое каталога\n"
    "2 - Статистика каталога\n"
    "3 - Поиск\n"
    "4 - Статистика атрибутов файлов\n"
    "5 - Вверх (в родительский каталог)\n"
    "6 - Вниз (в подкаталог)\n"
    "7 - Сменить диск\n"
    "8 - Специальные папки\n"
    "0 - Выход"
)


def check_windows_environment() -> bool:
    """Check for Windows; otherwise, display a message and exit."""
    if not utils.is_windows_os():
        print("Программа работает только в Windows.")
        sys.exit(1)
    return True


def display_windows_banner() -> None:
    """Banner: system and current disk."""
    print("=" * 50)
    print("  ФАЙЛОВЫЙ АРХЕОЛОГ  |  2142 г.")
    print(f"  ОС: {platform.system()} {platform.release()}") #ОС и версия
    print(f"  Текущий диск: {navigation.get_current_drive()}") # текущий диск
    print("=" * 50)


def display_main_menu(current_path: str) -> None:
    """Current path, drives, and commands."""
    print(f"\nПуть: {current_path}")
    print("Диски: " + " ".join(navigation.list_available_drives())) # показываем диски которые есть
    print(MENU)


def change_drive(current_path: str) -> str:
    """Command 7: switch to another disk."""
    drives = navigation.list_available_drives()
    answer = input(f"Диск {drives}: ").strip().upper().rstrip("\\") # спрашиваем диск и приводим к верхнему регистру
    if answer in drives:
        new_path = answer + "\\" # даем путь до диска
        if utils.validate_windows_path(new_path)[0]: # проверяем диск на доступность
            return new_path # вернем новый путь
    print("Диск недоступен.")
    return current_path # если недоступен, то вернем текущий путь


def go_to_special_folder(current_path: str) -> str:
    """Command 8: switch to a special folder."""
    folders = navigation.get_windows_special_folders() # словарь имя -> путь
    for name, path in folders.items(): # пары ключ значение
        print(f"  {name}: {path}") # покажем из чего выбирать
    answer = input("Куда перейти: ").strip().lower() # пользователь дает ответ
    for name, path in folders.items(): # теперь проходим для поиска
        if name.lower() == answer: # сравним с вводом
            return path # вернем новый путь
    print("Нет такой папки.") # если через условия не прошло
    return current_path # вернем то же где и находились


def handle_windows_navigation(command: str, current_path: str) -> str:
    """Commands 1, 5, 6, 7, 8. Returns the new current path."""
    match command:
        case "1":
            ok, items = navigation.list_directory(current_path) # список того что внутри
            if ok:
                navigation.format_directory_output(items, current_path) # покажем содержимое и путь
            else:
                print("Не удалось прочитать каталог.")
        case "5":
            return navigation.move_up(current_path) # вернем родителя(выше поднимемся)
        case "6":
            target = input("Имя подкаталога: ").strip() # спрашивает имя папки
            ok, new_path = navigation.move_down(current_path, target) # переместимся вниз
            if not ok:
                print("Нет такого каталога или нет доступа.")
            return new_path
        case "7":
            return change_drive(current_path) # смена диска. Вся работа в функции change_drive, она возвращает путь.
        case "8":
            return go_to_special_folder(current_path) # переместимся в специальную папку
    return current_path


def handle_windows_analysis(command: str, current_path: str) -> None:
    """Commands 2 and 4."""
    match command:
        case "2":
            analysis.show_windows_directory_stats(current_path) # общая статистика каталога
        case "4":
            stats = analysis.get_windows_file_attributes_stats(current_path) # словарь с числом файлов по атрибутам
            for name, count in stats.items(): # распаковка словаря
                print(f"  {name}: {count}")


def handle_windows_search(command: str, current_path: str) -> None:
    """Command 3: search menu, while the user continues."""
    while search.search_menu_handler(current_path): # показывает меню поиска из роли 4, истинно до результата вызова
        pass # чтобы тело цикла не было пустым


def run_windows_command(command: str, current_path: str) -> str:
    """Command routing. Returns the current path."""
    match command:
        case "1" | "5" | "6" | "7" | "8": # для любой из этих цифр
            return handle_windows_navigation(command, current_path) # Передаёт управление обработчику навигации и сразу возвращает его результат (новый путь или прежний). return завершает функцию, до последней строки дело не доходит.
        case "2" | "4": # для любой из этих цифр
            handle_windows_analysis(command, current_path) # Вызывает обработчик анализа. Он только печатает и ничего не возвращает, поэтому здесь нет return. Выполнение выходит из match и идёт на последнюю строку.
        case "3":
            handle_windows_search(command, current_path) # Вызывает обработчик поиска. Он тоже ничего не возвращает, и выполнение идёт на последнюю строку.
        case _: # для любого мусора из ввода
            print("Неизвестная команда.")
    return current_path


def main() -> NoReturn:
    """Main cycle"""
    check_windows_environment() # проверяем что на винде, если да, то скип
    display_windows_banner() # печатаем наш баннер
    current_path = os.getcwd() # путь старта
    while True:
        try:
            display_main_menu(current_path)
            command = input("> ").strip() # ждем ввод, очищаем от пробелов
            if command == "0": # закончим если пользователь выбрал выход
                break
            current_path = run_windows_command(command, current_path) # запускаем команды, обновляя путь
        except KeyboardInterrupt: # срабатывает если пользователь сделал Ctrl+C
            print("\nПрервано пользователем.")
            break
        except EOFError: # Срабатывает, когда ввод закончился (Ctrl+Z на Windows или завершённый поток ввода). Тоже выходим из цикла.
            break
        except Exception as error:  # для любых других ошибок
            print(f"Ошибка: {error}") # ошибка с описанием ошибки
    print("Раскопки завершены.")
    sys.exit(0) # завершение программы без ошибки


if __name__ == "__main__":
    main()

'''
__name__ — служебная переменная, в которую Python сам кладёт имя модуля.
При запуске python main.py в ней строка "__main__", условие истинно, и вызывается main().
Если другой файл делает import main, в __name__ будет "main", условие ложно, и программа не стартует сама.
'''