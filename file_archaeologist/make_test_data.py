"""Создаёт папку test_data для проверки проекта (рядом с этим файлом)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "test_data"
IS_WINDOWS = sys.platform == "win32"


def make_file(relative: str, size: int, text: str = "") -> Path:
    """Создаёт файл заданного размера в байтах."""
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    path.write_bytes(data + b"x" * max(0, size - len(data)))
    return path


def set_attrib(path: Path, flags: str) -> None:
    """Выставляет атрибуты Windows: +h скрытый, +s системный, +r чтение."""
    if IS_WINDOWS:
        subprocess.run(["attrib", *flags.split(), str(path)], check=False)


def main() -> None:
    ROOT.mkdir(exist_ok=True)

    make_file("docs/report.txt", 1024, "report")
    make_file("docs/notes.docx", 20480)
    make_file("docs/Читай меня.txt", 300, "кириллица в имени")
    make_file("media/photo.jpg", 1500000)
    make_file("media/song.mp3", 3 * 1024 * 1024)
    (ROOT / "media" / "empty_folder").mkdir(parents=True, exist_ok=True)
    make_file("programs/setup.exe", 2048)
    make_file("programs/lib.dll", 512)
    make_file("programs/run.bat", 80, "@echo hello")
    make_file("programs/tool.ps1", 120, "Write-Host hi")
    (ROOT / "MixedCase").mkdir(exist_ok=True)
    make_file("MixedCase/File.TXT", 10)
    make_file("deep/l1/l2/l3/l4/l5/l6/deep.txt", 50)
    make_file("duplicates/a.txt", 100, "same")
    make_file("duplicates/b.txt", 100, "same")

    set_attrib(make_file("secret/hidden.txt", 64), "+h")
    set_attrib(make_file("secret/system.dat", 64), "+s +h")
    set_attrib(make_file("secret/readonly.txt", 64), "+r")

    # длинный путь (больше 260 символов) - только на Windows
    if IS_WINDOWS:
        long_dir = str(ROOT)
        for index in range(12):
            long_dir = os.path.join(long_dir, f"long_directory_{index:02d}_" + "x" * 12)
        long_dir = "\\\\?\\" + long_dir
        os.makedirs(long_dir, exist_ok=True)
        with open(os.path.join(long_dir, "at_the_bottom.txt"), "w") as file:
            file.write("deep")
        print(f"Длинный путь создан, длина: {len(long_dir) - 4} символов")

    print(f"Готово: {ROOT}")


if __name__ == "__main__":
    main()
