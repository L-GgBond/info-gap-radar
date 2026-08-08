import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main():
    name = "info-gap-backend.exe" if sys.platform.startswith("win") else "info-gap-backend"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "-F",
            "main.py",
            "--name",
            name,
            "--noconsole",
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
