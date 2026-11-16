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
    print(f"  ОС: {platform.system()} {platform.release()}")
    print(f"  Текущий диск: {navigation.get_current_drive()}")
    print("=" * 50)


def display_main_menu(current_path: str) -> None:
    """Current path, drives, and commands."""
    print(f"\nПуть: {current_path}")
    print("Диски: " + " ".join(navigation.list_available_drives()))
    print(MENU)


def change_drive(current_path: str) -> str:
    """Command 7: switch to another disk."""
    drives = navigation.list_available_drives()
    answer = input(f"Диск {drives}: ").strip().upper().rstrip("\\")
    if answer in drives:
        new_path = answer + "\\"
        if utils.validate_windows_path(new_path)[0]:
            return new_path
    print("Диск недоступен.")
    return current_path


def go_to_special_folder(current_path: str) -> str:
    """Command 8: switch to a special folder."""
    folders = navigation.get_windows_special_folders()
    for name, path in folders.items():
        print(f"  {name}: {path}")
    answer = input("Куда перейти: ").strip().lower()
    for name, path in folders.items():
        if name.lower() == answer:
            return path
    print("Нет такой папки.")
    return current_path


def handle_windows_navigation(command: str, current_path: str) -> str:
    """Commands 1, 5, 6, 7, 8. Returns the new current path."""
    match command:
        case "1":
            ok, items = navigation.list_directory(current_path)
            if ok:
                navigation.format_directory_output(items, current_path)
            else:
                print("Не удалось прочитать каталог.")
        case "5":
            return navigation.move_up(current_path)
        case "6":
            target = input("Имя подкаталога: ").strip()
            ok, new_path = navigation.move_down(current_path, target)
            if not ok:
                print("Нет такого каталога или нет доступа.")
            return new_path
        case "7":
            return change_drive(current_path)
        case "8":
            return go_to_special_folder(current_path)
    return current_path


def handle_windows_analysis(command: str, current_path: str) -> None:
    """Commands 2 and 4."""
    match command:
        case "2":
            analysis.show_windows_directory_stats(current_path)
        case "4":
            stats = analysis.get_windows_file_attributes_stats(current_path)
            for name, count in stats.items():
                print(f"  {name}: {count}")


def handle_windows_search(command: str, current_path: str) -> None:
    """Command 3: search menu, while the user continues."""
    while search.search_menu_handler(current_path):
        pass


def run_windows_command(command: str, current_path: str) -> str:
    """Command routing. Returns the current path."""
    match command:
        case "1" | "5" | "6" | "7" | "8":
            return handle_windows_navigation(command, current_path)
        case "2" | "4":
            handle_windows_analysis(command, current_path)
        case "3":
            handle_windows_search(command, current_path)
        case _:
            print("Неизвестная команда.")
    return current_path


def main() -> NoReturn:
    """Main cycle"""
    check_windows_environment()
    display_windows_banner()
    current_path = os.getcwd()
    while True:
        try:
            display_main_menu(current_path)
            command = input("> ").strip()
            if command == "0":
                break
            current_path = run_windows_command(command, current_path)
        except KeyboardInterrupt:
            print("\nПрервано пользователем.")
            break
        except EOFError:
            break
        except Exception as error:
            print(f"Ошибка: {error}")
    print("Раскопки завершены.")
    sys.exit(0)


if __name__ == "__main__":
    main()