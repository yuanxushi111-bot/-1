"""Bundle the current CPython Windows installation without third-party packages."""
from pathlib import Path
import json
import platform
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tax_exam.common import ExamError, file_hash, inside, write_json


def bundle(root=ROOT):
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise ExamError("unsupported_runtime", "此脚本仅用于在 Windows x64 上生成同架构运行环境")
    base = Path(sys.base_prefix)
    target = inside(root, "runtime")
    target.mkdir(parents=True, exist_ok=True)
    version = f"python{sys.version_info.major}{sys.version_info.minor}"
    for filename in ("python.exe", "python3.dll", version + ".dll", "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        if (base / filename).exists():
            shutil.copyfile(base / filename, target / filename)
    dll_dir = target / "DLLs"
    dll_dir.mkdir(exist_ok=True)
    for file in (base / "DLLs").iterdir():
        if file.suffix.lower() in (".pyd", ".dll"):
            shutil.copyfile(file, dll_dir / file.name)
    excluded = {"site-packages", "__pycache__", "test", "tests", "idlelib", "tkinter", "turtledemo", "ensurepip"}
    # Stored archive permits bootstrap before zlib is imported; outer release zip compresses it.
    with zipfile.ZipFile(target / (version + ".zip"), "w", compression=zipfile.ZIP_STORED) as archive:
        for file in sorted((base / "Lib").rglob("*.py")):
            relative = file.relative_to(base / "Lib")
            if not any(part in excluded for part in relative.parts):
                archive.write(file, relative.as_posix())
    (target / (version + "._pth")).write_text(version + ".zip\nDLLs\n.\n", encoding="ascii")
    write_json(target / "runtime-manifest.json", {"python": platform.python_version(), "platform": "win32-x64", "origin": "local CPython standard library and binary distribution; no site-packages", "files": [{"path": file.relative_to(target).as_posix(), "sha256": file_hash(file)} for file in sorted(target.rglob("*")) if file.is_file() and file.name != "runtime-manifest.json"]})
    return {"runtime": str(target), "python": platform.python_version()}


if __name__ == "__main__":
    print(json.dumps(bundle(), ensure_ascii=False))
