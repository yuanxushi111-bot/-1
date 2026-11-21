"""Freeze installed distribution files into an isolated Windows dependency bundle."""
from pathlib import Path
import argparse
import base64
import csv
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tax_exam.common import ExamError, file_hash, inside, write_json
from prepare_mineru import prepare_interpreter


def bundle(site_packages):
    source = Path(site_packages).resolve()
    distributions = list(importlib.metadata.distributions(path=[str(source)]))
    mineru = next((dist for dist in distributions if dist.metadata["Name"].lower() == "mineru"), None)
    if mineru is None or mineru.version != "4.1.7":
        raise ExamError("incompatible_mineru", "准备包要求已安装的MinerU 4.1.7，不能打包未知环境")
    target = inside(ROOT, "runtime-mineru")
    if target.exists():
        raise ExamError("bundle_exists", "目标已存在，先核对已有依赖包；不覆盖使用中的环境")
    files, packages = {}, []
    for dist in distributions:
        packages.append({"name": dist.metadata["Name"], "version": dist.version, "license": dist.metadata.get("License-Expression") or dist.metadata.get("License", "See distribution metadata")})
        record = dist.read_text("RECORD")
        if not record:
            raise ExamError("missing_distribution_record", "无法验证某依赖的安装清单")
        for relative, hash_value, _ in csv.reader(record.splitlines()):
            candidate = (source / relative).resolve()
            if not candidate.is_relative_to(source):
                continue  # Venv launchers contain machine paths; use our portable entrypoint.
            clean = candidate.relative_to(source)
            if "__pycache__" in clean.parts or clean.suffix in {".pyc", ".pyo"} or clean.name in {"direct_url.json", "INSTALLER", "REQUESTED"}:
                continue
            if candidate.is_symlink() or not candidate.is_file():
                raise ExamError("invalid_distribution_file", "依赖文件缺失或包含符号链接")
            if hash_value.startswith("sha256="):
                actual = base64.urlsafe_b64encode(hashlib.sha256(candidate.read_bytes()).digest()).rstrip(b"=").decode()
                if actual != hash_value.split("=", 1)[1]:
                    raise ExamError("modified_dependency", "依赖与发行清单不符，拒绝打包")
            if clean.suffix == ".pth" and any(":\\" in line or ":/" in line for line in candidate.read_text(encoding="utf-8").splitlines()):
                raise ExamError("machine_specific_dependency", "依赖启动文件含本机路径")
            files[clean.as_posix()] = candidate
    for relative, candidate in sorted(files.items()):
        destination = inside(target, "site-packages/" + relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate, destination)
    executable = prepare_interpreter(target)
    result = subprocess.run([executable, str(ROOT / "scripts/mineru_entry.py"), "version", "--json"], capture_output=True, encoding="utf-8", timeout=60)
    if result.returncode or json.loads(result.stdout).get("mineru_version") != mineru.version:
        raise ExamError("bundled_mineru_failed", "独立运行环境中的MinerU启动校验失败")
    write_json(target / "third-party-manifest.json", {"python": sys.version.split()[0], "platform": "windows-x64", "packages": sorted(packages, key=lambda p: p["name"].lower()), "notice": "Original license files retained in each distribution's dist-info/licenses. Project MIT license does not replace dependency licenses."})
    pins = sorted({item["name"] + "==" + item["version"] for item in packages}, key=str.lower)
    (ROOT / "config/mineru-windows-py314.lock.txt").write_text("# Windows x64 / CPython 3.14: frozen from verified installed distributions.\n" + "\n".join(pins) + "\n", encoding="utf-8")
    entries = [{"path": p.relative_to(target).as_posix(), "sha256": file_hash(p)} for p in sorted(target.rglob("*")) if p.is_file() and "__pycache__" not in p.parts]
    write_json(target / "bundle-manifest.json", {"mineru_version": mineru.version, "models": None, "files": entries})
    return {"prepared": True, "files": len(entries), "packages": len(packages), "mineru": mineru.version, "models_included": False}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-packages", type=Path, required=True)
    print(json.dumps(bundle(parser.parse_args().site_packages), ensure_ascii=False))
