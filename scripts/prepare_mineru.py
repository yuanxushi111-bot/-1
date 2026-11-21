"""Explicit project-local MinerU preparation; no global environment modifications."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tax_exam.common import ExamError, file_hash, inside, write_json
from tax_exam.mineru_adapter import environment

MINERU_VERSION = "4.1.7"
PIP_VERSION = "25.3"


def prepare_interpreter(target):
    """Use a separate interpreter path so MinerU's spawned -m processes see its deps."""
    core = ROOT / "runtime"
    if sys.platform != "win32" or not (core / "python.exe").exists():
        return sys.executable
    target.mkdir(parents=True, exist_ok=True)
    version = f"python{sys.version_info.major}{sys.version_info.minor}"
    for file in core.iterdir():
        if file.name == "python.exe" or file.suffix == ".dll" or file.name == "LICENSE.txt":
            shutil.copyfile(file, target / file.name)
    (target / (version + "._pth")).write_text(f"../runtime/{version}.zip\n../runtime/DLLs\n.\nsite-packages\n", encoding="ascii")
    return str(target / "python.exe")


def prepare(install=False, models=None, enable_local=False):
    if not (install or models or enable_local):
        return {"planned": True, "mineru": MINERU_VERSION, "target": "runtime-mineru/site-packages", "network": "--install会联网下载依赖；--models显式下载模型", "changes_global_environment": False}
    if enable_local and not models:
        raise ExamError("models_required", "启用本地解析前须显式选择并校验模型资源")
    target = inside(ROOT, "runtime-mineru")
    target.mkdir(parents=True, exist_ok=True)
    packages = target / "site-packages"
    if not (packages / "mineru").is_dir():
        if not install:
            raise ExamError("dependencies_required", "先使用 --install 或私人包准备MinerU依赖")
        install_dependencies(target, packages)
    executable = prepare_interpreter(target)
    env = environment(ROOT)
    def run(*args):
        subprocess.run([executable, str(ROOT / "scripts/mineru_entry.py"), *args], env=env, check=True)
    run("version", "--json")
    if models:
        env["MINERU_MODEL_SOURCE"] = "auto"  # This explicit preparation action authorizes model downloads.
        kit = target / "run_kit.py"
        kit.write_text("import pathlib,sys,importlib.metadata\nsys.path.insert(0,str(pathlib.Path(__file__).parent/'site-packages'))\nep=next(e for e in importlib.metadata.distribution('mineru').entry_points if e.name=='mineru-kit')\nep.load()()\n", encoding="utf-8")
        subprocess.run([executable, str(kit), "models", "download", "--tier", models], env=env, check=True)
        subprocess.run([executable, str(kit), "models", "verify", "--tier", models], env=env, check=True)
        if enable_local:
            run("config", "set", "parse_server.local.managed_tier", models)
            run("config", "set", "parse_server.local.mode", "managed")
    files = [{"path": p.relative_to(target).as_posix(), "sha256": file_hash(p)} for p in sorted(target.rglob("*")) if p.is_file() and p.name not in {"bundle-manifest.json", "install-report.json", "run_pip.py", "run_kit.py"} and not p.name.endswith(".whl") and "__pycache__" not in p.parts]
    write_json(target / "bundle-manifest.json", {"mineru_version": MINERU_VERSION, "models": None, "files": files})
    return {"prepared": True, "mineru": MINERU_VERSION, "files": len(files), "models_prepared_locally": models, "models_in_dependency_bundle": False}


def install_dependencies(target, packages):
    metadata = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/pip/{PIP_VERSION}/json", timeout=30))
    wheel = next(item for item in metadata["urls"] if item["filename"].endswith(".whl"))
    wheel_path = target / wheel["filename"]
    if not wheel_path.exists():
        with urllib.request.urlopen(wheel["url"], timeout=60) as response:
            wheel_path.write_bytes(response.read())
    if file_hash(wheel_path) != wheel["digests"]["sha256"]:
        raise ExamError("download_hash_mismatch", "pip安装工具校验失败")
    runner = target / "run_pip.py"
    runner.write_text("import pathlib,runpy,sys\nsys.path.insert(0,str(next(pathlib.Path(__file__).parent.glob('pip-*.whl'))))\nrunpy.run_module('pip',run_name='__main__')\n", encoding="utf-8")
    report = target / "install-report.json"
    lockfile = ROOT / "config/mineru-windows-py314.lock.txt"
    requirements = ["-r", str(lockfile)] if sys.platform == "win32" and sys.version_info[:2] == (3, 14) and lockfile.exists() else [f"mineru=={MINERU_VERSION}"]
    subprocess.run([sys.executable, str(runner), "install", "--prefer-binary", "--no-compile", "--target", str(packages), "--report", str(report), *requirements], check=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--models", choices=["basic", "standard"])
    parser.add_argument("--enable-local", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(args.install, args.models, args.enable_local), ensure_ascii=False))
