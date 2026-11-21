"""Create separate public-source and private Windows releases from explicit allowlists."""
from pathlib import Path
import argparse
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tax_exam import __version__
from tax_exam.common import ExamError, file_hash, inside, load_json, write_json
from prepare_host import prepare

PUBLIC_FILES = ["README.md", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md", ".gitignore", ".gitattributes", "pyproject.toml", "tax_exam.py", "tools.cmd", "检查安装.cmd", "准备MinerU.cmd"]
PUBLIC_DIRS = ["src", "skills", "scripts", "docs", "schemas", "config", "examples", "tests", ".github"]


def source_files(root):
    files = [inside(root, name) for name in PUBLIC_FILES]
    for directory in PUBLIC_DIRS:
        files.extend(file for file in inside(root, directory).rglob("*") if file.is_file() and "__pycache__" not in file.parts and file.suffix not in (".pyc", ".pyo"))
    if any(not file.is_file() for file in files):
        raise ExamError("missing_release_file", "发布白名单包含尚未生成的必要文件")
    return sorted(set(files))


def package(root=ROOT, private=False):
    root = Path(root).resolve()
    prepare(root)
    files = source_files(root)
    # Include generated discovery directory; public package has no private materials.
    files += [file for file in inside(root, ".dsh/skills").rglob("*") if file.is_file()]
    if private:
        manifest = load_json(root / "library/manifest.json")
        for item in manifest["files"]:
            file = inside(root, item["path"])
            if file_hash(file) != item["sha256"]:
                raise ExamError("modified_release_material", "资料已变化，请重新导入后打包")
            files.append(file)
        files.append(root / "library/manifest.json")
        files.append(root / "indexes/materials.sqlite")
        from tax_exam.recitation import catalog, load
        deck = catalog(root)
        for card_id, version in deck["current"].items():
            load(root, card_id, version)
        for item in deck["files"]:
            file = inside(root, item["path"])
            if file_hash(file) != item["sha256"]:
                raise ExamError("modified_card", "背诵卡文件校验失败")
            files.append(file)
        if (root / "library/recitation-manifest.json").exists():
            files.append(root / "library/recitation-manifest.json")
        for archive in (root / "library/history").glob("*/manifest.json"):
            old = load_json(archive)
            for item in old["files"]:
                file = inside(archive.parent, item["path"])
                if file_hash(file) != item["sha256"]:
                    raise ExamError("modified_history", "历史资料校验失败")
                files.append(file)
            files.append(archive)
            if (archive.parent / "materials.sqlite").is_file():
                files.append(archive.parent / "materials.sqlite")
        runtime = load_json(root / "runtime/runtime-manifest.json")
        for item in runtime["files"]:
            file = inside(root / "runtime", item["path"])
            if file_hash(file) != item["sha256"]:
                raise ExamError("modified_runtime", "运行环境校验失败")
            files.append(file)
        files.append(root / "runtime/runtime-manifest.json")
        mineru = load_json(root / "runtime-mineru/bundle-manifest.json")
        for item in mineru["files"]:
            file = inside(root / "runtime-mineru", item["path"])
            if file_hash(file) != item["sha256"]:
                raise ExamError("modified_mineru_runtime", "MinerU依赖包校验失败")
            files.append(file)
        files.append(root / "runtime-mineru/bundle-manifest.json")
    files = sorted(set(files))
    name = f"tax-exam-skill-{__version__}-" + ("windows-x64-private" if private else "public-source")
    paths = [file.relative_to(root).as_posix() for file in files]
    if any(path.startswith(("userdata/", ".git/")) or Path(path).name.startswith((".env", "config.local")) for path in paths):
        raise ExamError("private_data_in_release", "发布清单意外包含个人记录或本机配置")
    dist = inside(root, "dist")
    dist.mkdir(parents=True, exist_ok=True)
    inventory = {"version": __version__, "flavor": "private" if private else "public-source", "contains_host": False, "host": "deepseekharness", "contains_personal_records": False, "contains_mineru_dependencies": private, "contains_mineru_models": False, "files": [{"path": path, "sha256": file_hash(file)} for file, path in zip(files, paths)]}
    inventory["starter_recitation_cards"] = len(deck["current"]) if private else 0
    target = dist / (name + ".zip")
    temporary = dist / (name + ".building.zip")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file, relative in zip(files, paths):
            archive.write(file, name + "/" + relative)
        archive.writestr(name + "/release-manifest.json", json.dumps(inventory, ensure_ascii=False, indent=2))
    temporary.replace(target)
    write_json(dist / (name + ".manifest.json"), inventory)
    write_json(dist / (name + ".sha256.json"), {"file": target.name, "sha256": file_hash(target), "bytes": target.stat().st_size})
    return {"file": str(target), "bytes": target.stat().st_size, "files": len(files), "sha256": file_hash(target)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", action="store_true")
    args = parser.parse_args()
    print(json.dumps(package(private=args.private), ensure_ascii=False))
