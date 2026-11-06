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
    "8 - Дерево каталогов\n"
    "9 - Специальные папки\n"
    "0 - Выход"
)


def check_windows_environment() -> bool:
    """Проверка Windows; иначе сообщение и выход."""
    if not utils.is_windows_os():
        print("Программа работает только в Windows.")
        sys.exit(1)
    return True


def display_windows_banner() -> None:
    """Баннер: система и текущий диск."""
    print("=" * 50)
    print("  ФАЙЛОВЫЙ АРХЕОЛОГ  |  2142 г.")
    print(f"  ОС: {platform.system()} {platform.release()}")
    print(f"  Текущий диск: {navigation.get_current_drive()}")
    print("=" * 50)


def display_main_menu(current_path: str) -> None:
    """Текущий путь, диски и команды."""
    print(f"\nПуть: {current_path}")
    print("Диски: " + " ".join(navigation.list_available_drives()))
    print(MENU)


def change_drive(current_path: str) -> str:
    """Команда 7: переход на другой диск."""
    drives = navigation.list_available_drives()
    answer = input(f"Диск {drives}: ").strip().upper().rstrip("\\")
    if answer in drives:
        new_path = answer + "\\"
        if utils.validate_windows_path(new_path)[0]:
            return new_path
    print("Диск недоступен.")
    return current_path


def show_tree(current_path: str) -> None:
    """Команда 8: дерево каталогов."""
    answer = input("Глубина дерева (по умолчанию 2): ").strip()
    depth = int(answer) if answer.isdigit() else 2
    tree = navigation.build_windows_tree_recursive(
        current_path, max_depth=depth)
    print(tree["name"])
    print("\n".join(navigation.format_tree(tree)))


def go_to_special_folder(current_path: str) -> str:
    """Команда 9: переход в специальную папку."""
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
    """Команды 1, 5, 6, 7, 8, 9. Возвращает новый текущий путь."""
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
            show_tree(current_path)
        case "9":
            return go_to_special_folder(current_path)
    return current_path


def handle_windows_analysis(command: str, current_path: str) -> None:
    """Команды 2 и 4."""
    match command:
        case "2":
            analysis.show_windows_directory_stats(current_path)
        case "4":
            stats = analysis.get_windows_file_attributes_stats(current_path)
            for name, count in stats.items():
                print(f"  {name}: {count}")


def handle_windows_search(command: str, current_path: str) -> None:
    """Команда 3: меню поиска, пока пользователь продолжает."""
    while search.search_menu_handler(current_path):
        pass


def run_windows_command(command: str, current_path: str) -> str:
    """Маршрутизация команд. Возвращает текущий путь."""
    match command:
        case "1" | "5" | "6" | "7" | "8" | "9":
            return handle_windows_navigation(command, current_path)
        case "2" | "4":
            handle_windows_analysis(command, current_path)
        case "3":
            handle_windows_search(command, current_path)
        case _:
            print("Неизвестная команда.")
    return current_path


def main() -> NoReturn:
    """Главный цикл."""
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
        except Exception as error:  # верхнеуровневая защита
            print(f"Ошибка: {error}")
    print("Раскопки завершены.")
    sys.exit(0)


if __name__ == "__main__":
    main()