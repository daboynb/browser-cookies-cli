"""Build portable packages for Windows, Linux, and macOS.

    python build_portable.py          # build all platforms
    python build_portable.py win64    # build one platform

Windows: bundles Python embeddable + deps (zero requirements)
Linux/macOS: bundles deps only (requires system python3, no pip needed)
"""

import shutil
import subprocess
import sys
import tempfile
import urllib.request
import venv
import zipfile
from pathlib import Path

PYTHON_VERSION = "3.12.10"
PYTHON_TAG = "312"
EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-embed-amd64.zip"
)

PLATFORMS = {
    "win64": {
        "pip_platform": "win_amd64",
        "deps": ["cryptography", "pywin32"],
        "embed_python": True,
    },
    "linux-x64": {
        "pip_platform": "manylinux2014_x86_64",
        "deps": ["cryptography", "secretstorage"],
        "embed_python": False,
    },
    "macos-x64": {
        "pip_platform": "macosx_10_12_x86_64",
        "deps": ["cryptography"],
        "embed_python": False,
    },
    "macos-arm64": {
        "pip_platform": "macosx_11_0_arm64",
        "deps": ["cryptography"],
        "embed_python": False,
    },
}


def _download(url, dest):
    print(f"  {Path(dest).name} ← {url.split('/')[-1]}")
    urllib.request.urlretrieve(url, dest)


def _get_venv_pip(venv_dir):
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "pip.exe"
    return venv_dir / "bin" / "pip"


def _download_wheels(venv_pip, wheels_dir, platform, deps):
    subprocess.run(
        [
            str(venv_pip), "download",
            "--dest", str(wheels_dir),
            "--platform", platform,
            "--python-version", PYTHON_TAG,
            "--only-binary", ":all:",
            *deps,
        ],
        check=True, capture_output=True,
    )


def _extract_wheels(wheels_dir, site_packages):
    site_packages.mkdir(parents=True, exist_ok=True)
    for whl in sorted(wheels_dir.glob("*.whl")):
        print(f"    {whl.name}")
        with zipfile.ZipFile(whl) as zf:
            zf.extractall(site_packages)


def _copy_project(project_root, dest):
    shutil.copytree(
        project_root, dest,
        ignore=shutil.ignore_patterns(
            "tests", "__pycache__", "*.pyc", "Dockerfile", ".git",
            ".github", "CLAUDE.md", "*.zip",
        ),
    )


def build_windows(project_root, build_dir, venv_pip):
    name = "browser-cookies-portable-win64"
    pkg = build_dir / name
    py_dir = pkg / "python"
    site_pkg = py_dir / "Lib" / "site-packages"

    # Python embeddable
    print("  Downloading Python embeddable...")
    embed_zip = build_dir / "python-embed.zip"
    _download(EMBED_URL, embed_zip)
    with zipfile.ZipFile(embed_zip) as zf:
        zf.extractall(py_dir)

    pth = py_dir / f"python{PYTHON_TAG}._pth"
    pth.write_text(f"python{PYTHON_TAG}.zip\n.\nLib\\site-packages\nimport site\n")

    # Deps
    wheels_dir = build_dir / "wheels_win"
    wheels_dir.mkdir()
    _download_wheels(venv_pip, wheels_dir, "win_amd64", PLATFORMS["win64"]["deps"])
    _extract_wheels(wheels_dir, site_pkg)

    # pywin32 DLLs
    for dll in site_pkg.rglob("*.dll"):
        if "pywintypes" in dll.name or "pythoncom" in dll.name:
            shutil.copy2(dll, py_dir)

    # Project
    _copy_project(project_root / "browser_cookies_cli", site_pkg / "browser_cookies_cli")

    # Scripts
    (pkg / "export.bat").write_text(
        '@echo off\r\ncd /d "%~dp0"\r\n'
        'python\\python.exe -m browser_cookies_cli export %*\r\n'
        'if %ERRORLEVEL% NEQ 0 pause\r\n'
    )
    (pkg / "import.bat").write_text(
        '@echo off\r\ncd /d "%~dp0"\r\n'
        'python\\python.exe -m browser_cookies_cli import %*\r\n'
        'if %ERRORLEVEL% NEQ 0 pause\r\n'
    )

    out = project_root / f"{name}.zip"
    shutil.make_archive(str(out).replace(".zip", ""), "zip", build_dir, name)
    return out


def build_unix(project_root, build_dir, venv_pip, platform_key):
    cfg = PLATFORMS[platform_key]
    name = f"browser-cookies-portable-{platform_key}"
    pkg = build_dir / name
    lib_dir = pkg / "lib"

    # Deps
    wheels_dir = build_dir / f"wheels_{platform_key.replace('-', '_')}"
    wheels_dir.mkdir()
    _download_wheels(venv_pip, wheels_dir, cfg["pip_platform"], cfg["deps"])
    _extract_wheels(wheels_dir, lib_dir)

    # Project
    _copy_project(project_root / "browser_cookies_cli", lib_dir / "browser_cookies_cli")

    # Scripts
    export_sh = pkg / "export.sh"
    export_sh.write_text(
        '#!/usr/bin/env bash\n'
        'DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'PYTHONPATH="$DIR/lib" python3 -m browser_cookies_cli export "$@"\n'
    )
    export_sh.chmod(0o755)

    import_sh = pkg / "import.sh"
    import_sh.write_text(
        '#!/usr/bin/env bash\n'
        'DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'PYTHONPATH="$DIR/lib" python3 -m browser_cookies_cli import "$@"\n'
    )
    import_sh.chmod(0o755)

    out = project_root / f"{name}.tar.gz"
    shutil.make_archive(str(out).replace(".tar.gz", ""), "gztar", build_dir, name)
    return out


def main():
    project_root = Path(__file__).resolve().parent.parent
    targets = sys.argv[1:] or list(PLATFORMS)

    for t in targets:
        if t not in PLATFORMS:
            print(f"Unknown platform: {t}. Available: {', '.join(PLATFORMS)}")
            sys.exit(1)

    build_dir = Path(tempfile.mkdtemp(prefix="bcb_"))
    venv_dir = build_dir / "venv"
    venv.create(str(venv_dir), with_pip=True)
    venv_pip = _get_venv_pip(venv_dir)

    try:
        for target in targets:
            print(f"\n=== Building {target} ===")
            if target == "win64":
                out = build_windows(project_root, build_dir, venv_pip)
            else:
                out = build_unix(project_root, build_dir, venv_pip, target)
            size = out.stat().st_size / 1024 / 1024
            print(f"  → {out.name} ({size:.1f} MB)")
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)

    print("\nDone!")


if __name__ == "__main__":
    main()
