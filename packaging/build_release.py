"""Reproducible Windows release builder for Computer-Auto v2.0.

Default (Tauri v2 + React + 3D Mascot):
  1. Builds the React + Tailwind + Three.js frontend (`npm --prefix ui run build`).
  2. Builds the Rust + Tauri v2 app & NSIS Windows Installer (`npx --prefix ui tauri build --bundles nsis`).
  3. Copies `Computer-Auto-Setup.exe` and `Computer-Auto.exe` into `release_dist/`.
  4. Audits `release_dist/` to guarantee zero `.env`, `settings.json`, API keys, or `models/` weights.

Fallback (`--pyinstaller`):
  Builds a window-only (`--noconsole`) PyInstaller binary and portable zip in `release_dist/`.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
UI_DIR = ROOT_DIR / "ui"
TAURI_DIR = ROOT_DIR / "src-tauri"
TAURI_RELEASE_DIR = TAURI_DIR / "target" / "release"
NSIS_BUNDLE_DIR = TAURI_RELEASE_DIR / "bundle" / "nsis"

RELEASE_DIR = ROOT_DIR / "release_dist"
BUILD_WORK_DIR = ROOT_DIR / "build" / "pyinstaller"
DIST_WORK_DIR = ROOT_DIR / "dist" / "pyinstaller"

APP_NAME = "Computer-Auto"
SETUP_EXE_NAME = "Computer-Auto-Setup.exe"
STANDALONE_EXE_NAME = "Computer-Auto.exe"
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
API_KEY_PATTERN = re.compile(rb"sk-or-v1-[A-Za-z0-9]{16,}")


def _resolve_tool(name: str) -> str:
    """Resolve CLI executable path (handles .cmd shims on Windows)."""
    return shutil.which(name) or name


def _assert_no_secrets_or_weights(paths: list[Path], base_dir: Path | None = None) -> None:
    """Abort if any secret, user settings, log, model weight, or API key is staged."""
    for p in paths:
        rel = p.relative_to(base_dir) if base_dir and p.is_absolute() else p
        parts_lower = {part.lower() for part in rel.parts}
        if parts_lower & FORBIDDEN_NAMES:
            raise RuntimeError(f"Refusing to bundle forbidden path: {rel}")
        if rel.suffix.lower() in FORBIDDEN_SUFFIXES:
            raise RuntimeError(f"Refusing to bundle forbidden file type: {rel}")
        if p.is_file() and p.suffix.lower() not in {".exe", ".msi", ".dll", ".zip"}:
            try:
                content = p.read_bytes()
            except OSError:
                continue
            if API_KEY_PATTERN.search(content):
                raise RuntimeError(f"Refusing to bundle file containing OpenRouter API key: {rel}")


def audit_release_dir(release_dir: Path = RELEASE_DIR) -> list[Path]:
    """Audit release_dist/ to guarantee zero secrets, settings, logs, or model weights."""
    if not release_dir.exists():
        return []
    files = [p for p in release_dir.rglob("*") if p.is_file()]
    _assert_no_secrets_or_weights(files, base_dir=release_dir)
    return files


def build_frontend() -> Path:
    """Build the React + Tailwind + Three.js 3D Mascot frontend into ui/dist."""
    npm = _resolve_tool("npm")
    cmd = [npm, "--prefix", str(UI_DIR), "run", "build"]
    print("Building frontend:")
    print(" ", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT_DIR), check=True)
    dist_dir = UI_DIR / "dist"
    if not dist_dir.is_dir():
        raise FileNotFoundError(f"Expected frontend build output at {dist_dir}")
    return dist_dir


def build_tauri() -> tuple[Path | None, Path]:
    """Build the Rust + Tauri v2 application and NSIS Windows Installer."""
    npx = _resolve_tool("npx")
    cmd = [npx, "--yes", "@tauri-apps/cli@^2", "build", "--bundles", "nsis"]
    print("Building Tauri v2 + NSIS installer:")
    print(" ", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT_DIR), check=True)

    standalone_exe = TAURI_RELEASE_DIR / STANDALONE_EXE_NAME
    if not standalone_exe.is_file():
        raise FileNotFoundError(f"Expected Tauri GUI binary at {standalone_exe}")

    setup_candidates = sorted(NSIS_BUNDLE_DIR.glob("*-setup.exe")) if NSIS_BUNDLE_DIR.is_dir() else []
    setup_exe = setup_candidates[0] if setup_candidates else None
    return setup_exe, standalone_exe


def stage_tauri_release(setup_exe: Path | None, standalone_exe: Path) -> list[Path]:
    """Copy Tauri v2 NSIS installer and standalone GUI binary into release_dist/."""
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []

    if setup_exe is not None and setup_exe.is_file():
        dest_setup = RELEASE_DIR / SETUP_EXE_NAME
        shutil.copy2(setup_exe, dest_setup)
        staged.append(dest_setup)

    if standalone_exe.is_file():
        dest_exe = RELEASE_DIR / STANDALONE_EXE_NAME
        shutil.copy2(standalone_exe, dest_exe)
        staged.append(dest_exe)

    if not staged:
        raise FileNotFoundError("No Tauri release binaries found to stage into release_dist/")

    audit_release_dir(RELEASE_DIR)
    for item in staged:
        print(f"Staged release artifact: {item} ({item.stat().st_size / (1024 * 1024):.1f} MB)")
    return staged


def build_pyinstaller_executable() -> Path:
    """Fallback: invoke PyInstaller (--noconsole) to produce Computer-Auto.exe."""
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
        "--noconsole",
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

    print("Running PyInstaller fallback (--noconsole):")
    print(" ", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT_DIR), check=True)

    exe_name = STANDALONE_EXE_NAME if sys.platform == "win32" else APP_NAME
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
    _assert_no_secrets_or_weights(staged_files, base_dir=stage_dir)

    zip_path = RELEASE_DIR / ZIP_NAME
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(staged_files):
            arcname = Path(APP_NAME) / file_path.relative_to(stage_dir)
            zf.write(file_path, arcname=str(arcname))

    with zipfile.ZipFile(zip_path, "r") as zf:
        entries = [Path(name) for name in zf.namelist()]
        try:
            _assert_no_secrets_or_weights(entries)
        except Exception:
            zip_path.unlink(missing_ok=True)
            raise

    audit_release_dir(RELEASE_DIR)
    print(f"Created portable release: {zip_path} ({zip_path.stat().st_size / (1024 * 1024):.1f} MB)")
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Computer-Auto v2.0 Windows release")
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip compiling and stage existing build artifacts into release_dist/",
    )
    parser.add_argument(
        "--pyinstaller",
        action="store_true",
        help="Use legacy PyInstaller (--noconsole) portable zip fallback instead of Tauri v2",
    )
    args = parser.parse_args()

    if args.pyinstaller:
        exe_name = STANDALONE_EXE_NAME if sys.platform == "win32" else APP_NAME
        exe_path = DIST_WORK_DIR / exe_name
        if not args.skip_build:
            exe_path = build_pyinstaller_executable()
        elif not exe_path.is_file():
            raise FileNotFoundError(f"--skip-build specified, but {exe_path} does not exist")
        package_zip(exe_path)
        return

    if not args.skip_build:
        build_frontend()
        setup_exe, standalone_exe = build_tauri()
    else:
        setup_candidates = sorted(NSIS_BUNDLE_DIR.glob("*-setup.exe")) if NSIS_BUNDLE_DIR.is_dir() else []
        setup_exe = setup_candidates[0] if setup_candidates else None
        standalone_exe = TAURI_RELEASE_DIR / STANDALONE_EXE_NAME

    stage_tauri_release(setup_exe, standalone_exe)


if __name__ == "__main__":
    main()
