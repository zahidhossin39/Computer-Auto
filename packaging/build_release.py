"""Reproducible Windows portable release builder for Computer-Auto.

Builds Computer-Auto.exe via PyInstaller and packages a clean portable zip in
`release_dist/` containing:
  - Computer-Auto.exe
  - intents.yaml
  - README.md
  - scripts/download_models.py

Strictly NEVER bundles .env, settings.json, logs/, or models/.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
RELEASE_DIR = ROOT_DIR / "release_dist"
BUILD_WORK_DIR = ROOT_DIR / "build" / "pyinstaller"
DIST_WORK_DIR = ROOT_DIR / "dist" / "pyinstaller"

APP_NAME = "Computer-Auto"
ZIP_NAME = "Computer-Auto-Windows-Portable.zip"

HIDDEN_IMPORTS = [
    "sherpa_onnx",
    "sounddevice",
    "win32com",
    "win32com.client",
    "pythoncom",
    "pywintypes",
    "win32api",
    "win32gui",
    "win32con",
    "win32process",
    "win32clipboard",
    "uiautomation",
    "pynput",
    "pynput.keyboard",
    "pynput.mouse",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "mss",
    "yaml",
    "tkinter",
    "tkinter.ttk",
    "dotenv",
    "requests",
    "numpy",
    "scipy",
]

FORBIDDEN_NAMES = {
    ".env",
    ".env.local",
    "settings.json",
    "logs",
    "models",
}
FORBIDDEN_SUFFIXES = {".key", ".onnx", ".log"}


def _assert_no_secrets_or_weights(paths: list[Path]) -> None:
    """Abort if any secret, user settings, log, or model weight is staged."""
    for p in paths:
        parts_lower = {part.lower() for part in p.parts}
        if parts_lower & FORBIDDEN_NAMES:
            raise RuntimeError(f"Refusing to bundle forbidden path: {p}")
        if p.suffix.lower() in FORBIDDEN_SUFFIXES:
            raise RuntimeError(f"Refusing to bundle forbidden file type: {p}")


def build_executable() -> Path:
    """Invoke PyInstaller to produce Computer-Auto.exe."""
    BUILD_WORK_DIR.mkdir(parents=True, exist_ok=True)
    DIST_WORK_DIR.mkdir(parents=True, exist_ok=True)

    sep = ";" if sys.platform == "win32" else ":"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        APP_NAME,
        "--distpath",
        str(DIST_WORK_DIR),
        "--workpath",
        str(BUILD_WORK_DIR),
        "--specpath",
        str(BUILD_WORK_DIR),
        "--add-data",
        f"{ROOT_DIR / 'intents.yaml'}{sep}.",
        "--collect-all",
        "sherpa_onnx",
        "--collect-all",
        "sounddevice",
    ]
    for mod in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", mod])

    cmd.append(str(ROOT_DIR / "main.py"))

    print("Running PyInstaller:")
    print(" ", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT_DIR), check=True)

    exe_name = f"{APP_NAME}.exe" if sys.platform == "win32" else APP_NAME
    exe_path = DIST_WORK_DIR / exe_name
    if not exe_path.is_file():
        raise FileNotFoundError(f"Expected built executable at {exe_path}")
    return exe_path


def package_zip(exe_path: Path) -> Path:
    """Assemble clean portable release folder and zip it into release_dist/."""
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    stage_dir = BUILD_WORK_DIR / "stage" / APP_NAME
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)

    # Copy only explicitly allowlisted release files
    shutil.copy2(exe_path, stage_dir / exe_path.name)
    shutil.copy2(ROOT_DIR / "intents.yaml", stage_dir / "intents.yaml")
    shutil.copy2(ROOT_DIR / "README.md", stage_dir / "README.md")

    scripts_dest = stage_dir / "scripts"
    scripts_dest.mkdir(exist_ok=True)
    shutil.copy2(
        ROOT_DIR / "scripts" / "download_models.py",
        scripts_dest / "download_models.py",
    )

    staged_files = [p for p in stage_dir.rglob("*") if p.is_file()]
    _assert_no_secrets_or_weights([p.relative_to(stage_dir) for p in staged_files])

    zip_path = RELEASE_DIR / ZIP_NAME
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(staged_files):
            arcname = Path(APP_NAME) / file_path.relative_to(stage_dir)
            zf.write(file_path, arcname=str(arcname))

    # Post-zip audit
    with zipfile.ZipFile(zip_path, "r") as zf:
        entries = [Path(name) for name in zf.namelist()]
        try:
            _assert_no_secrets_or_weights(entries)
        except Exception:
            zip_path.unlink(missing_ok=True)
            raise

    print(f"Created portable release: {zip_path} ({zip_path.stat().st_size / (1024 * 1024):.1f} MB)")
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Computer-Auto portable Windows release")
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip PyInstaller and re-zip existing dist/pyinstaller/Computer-Auto.exe",
    )
    args = parser.parse_args()

    exe_name = f"{APP_NAME}.exe" if sys.platform == "win32" else APP_NAME
    exe_path = DIST_WORK_DIR / exe_name
    if not args.skip_build:
        exe_path = build_executable()
    elif not exe_path.is_file():
        raise FileNotFoundError(f"--skip-build specified, but {exe_path} does not exist")

    package_zip(exe_path)


if __name__ == "__main__":
    main()
