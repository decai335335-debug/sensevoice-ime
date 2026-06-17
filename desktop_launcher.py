import subprocess
import sys
from pathlib import Path
from tkinter import messagebox


def find_project_root():
    candidates = []
    candidates.extend([Path.cwd().resolve(), *Path.cwd().resolve().parents])
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        candidates.extend([exe_path.parent, *exe_path.parents])
    script_path = Path(__file__).resolve()
    candidates.extend([script_path.parent, *script_path.parents])

    for candidate in candidates:
        if (candidate / "desktop_app.py").exists() and (candidate / "sensevoice_ime.py").exists():
            return candidate
    return None


def main():
    root = find_project_root()
    if root is None:
        messagebox.showerror("SenseVoice IME", "找不到 sensevoice_ime 项目目录。请把 EXE 放在项目目录或 dist 目录里运行。")
        return 2

    pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    python = root / ".venv" / "Scripts" / "python.exe"
    if not pythonw.exists():
        pythonw = root / "venv" / "Scripts" / "pythonw.exe"
        python = root / "venv" / "Scripts" / "python.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)
        python = Path(sys.executable)

    desktop_app = root / "desktop_app.py"
    try:
        subprocess.Popen([str(pythonw), str(desktop_app)], cwd=str(root))
    except Exception as exc:
        try:
            subprocess.Popen([str(python), str(desktop_app)], cwd=str(root))
        except Exception:
            messagebox.showerror("SenseVoice IME", f"启动桌面程序失败：\n{exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
