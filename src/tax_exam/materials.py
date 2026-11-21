"""Portable material ingestion, original-version archives, and source roles."""
from pathlib import Path
import os
import re
import shutil
from urllib.parse import quote, unquote

from .common import ExamError, atomic_write, digest, file_hash, inside, load_json, lock, write_json

BOOKS = {
    "15539476.md": ("international-tax-primer-5", "国际税收基础（第五版·中英双语，2024）"),
    "国际税法学_12077563(1).md": ("international-tax-liao-2008", "国际税法学（廖益新，2008）"),
    "国际税法学   第4版,刘剑文主编,2020_14764363.md": ("international-tax-liu-2020", "国际税法学（刘剑文，第四版，2020）"),
    "税法原理 第十一版 张守文 可复制搜索.md": ("tax-principles-11", "税法原理（张守文，第十一版，2024）"),
}
ROLES = {"textbook", "lecture", "bilingual_notes", "guide", "usage_note", "exam", "answers"}
LINK = re.compile(r"!?\[([^\]]*)\]\(([^)\n]+)\)")


def archive_current(root):
    """Archive only manifest-listed files, not user settings or working directories."""
    root = Path(root)
    path = root / "library/manifest.json"
    if not path.exists():
        return None
    old = load_json(path)
    key = file_hash(path)
    archive = inside(root, "library/history/" + key)
    if (archive / "manifest.json").exists():
        return key
    for item in old["files"]:
        source = inside(root, item["path"])
        if not source.is_file() or file_hash(source) != item["sha256"]:
            raise ExamError("archive_source_changed", "旧资料已被手工修改；先保存修改再重建，不能伪造旧版引用")
        target = inside(archive, item["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    db = root / "indexes/materials.sqlite"
    if db.exists():
        shutil.copyfile(db, archive / "materials.sqlite")
    write_json(archive / "manifest.json", old)
    return key


def source_info(path, relative):
    name = path.name
    role = "textbook"
    source_id, title = BOOKS.get(name, ("source-" + digest(relative.as_posix())[:16], path.stem))
    extra = {}
    if "真题和答案" in relative.parts or re.match(r"20\d\d年.*初试", name):
        year = int(re.search(r"20\d{2}", name)[0])
        role = "exam" if "真题" in name else "answers"
        source_id = f"xmu-{year}-{role}"
        extra["year"] = year
    elif "重点" in relative.parts:
        role = "guide"
        source_id = "guide-" + digest(relative.as_posix())[:12]
        if "批注版" in name:
            extra["derived_from"] = "lecture-yanming-2026" if "严明" in name else "original-textbook"
    elif "其他" in relative.parts:
        role = "usage_note"
    elif "严明法学讲义" in name:
        role, source_id = "lecture", "lecture-yanming-2026"
    elif "中英文对照" in name:
        role = "bilingual_notes"
    return {"id": source_id, "title": title, "role": role, **extra}


def _freeze_files(source_root, selected):
    """Build a sanitized in-memory map; do not modify source documents."""
    source_root = Path(source_root).resolve()
    content, warnings = {}, []

    def freeze(path):
        path = path.resolve()
        if not path.is_relative_to(source_root) or any("备份" in p for p in path.relative_to(source_root).parts):
            raise ExamError("unsafe_asset", "附件超出指定资料目录或属于备份")
        key = path.relative_to(source_root).as_posix()
        if key in content:
            return
        raw = path.read_bytes()
        content[key] = raw  # Mark visited before following cyclic note links.
        if path.suffix.lower() != ".md":
            return
        text = raw.decode("utf-8-sig")

        def rewrite(match):
            label, raw_link = match[1], match[2]
            link, separator, fragment = unquote(raw_link.strip().strip("<>")).partition("#")
            if not link:
                return match[0]
            absolute = bool(re.match(r"^[A-Za-z]:[/\\]", link)) or Path(link).is_absolute() or link.lower().startswith("file:")
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", link) and not absolute:
                return match[0]
            asset = (path.parent / link).resolve()
            if absolute or not asset.is_relative_to(source_root):
                replacement = source_root / "教材" / (Path(link).stem + ".md")
                if not absolute and replacement.name in BOOKS and replacement.exists():
                    freeze(replacement)
                    relative = quote(os.path.relpath(replacement, path.parent).replace("\\", "/"), safe="/")
                    warnings.append({"file": key, "issue": "pdf_link_redirected_to_markdown"})
                    return f"[{label}]({relative}{separator}{fragment})"
                warnings.append({"file": key, "issue": "machine_specific_or_external_file_link_removed"})
                return label + "（原件未随包）"
            if not asset.is_file():
                raise ExamError("missing_asset", f"本地引用目标不存在：{key}，请先修复再导入")
            if any("备份" in p for p in asset.relative_to(source_root).parts):
                warnings.append({"file": key, "issue": "backup_link_not_imported"})
                return label + "（历史备份未随包）"
            freeze(asset)
            return match[0]

        text = LINK.sub(rewrite, text)
        content[key] = text.encode("utf-8")

    for path in selected:
        freeze(path)
    return content, warnings


def _install(root, content, entries, warnings, replace=False):
    from .library import build_index
    root = Path(root).resolve()
    library = inside(root, "library")
    with lock(library / "write.lock"):
        old = load_json(library / "manifest.json") if (library / "manifest.json").exists() else {"schema_version": 1, "sources": [], "files": [], "warnings": []}
        # A no-op import keeps citation hashes and caches stable.
        new_sources = [] if replace else list(old["sources"])
        by_id = {item["id"]: item for item in new_sources}
        for entry in entries:
            entry["sha256"] = digest(content[entry.pop("_relative")])
            by_id[entry["id"]] = entry
        sources = sorted(by_id.values(), key=lambda item: item["id"])
        file_map = {} if replace else {item["path"]: item for item in old["files"]}
        for relative, data in content.items():
            package_path = "library/sources/" + relative
            file_map[package_path] = {"path": package_path, "sha256": digest(data)}
        result = {"schema_version": 1, "sources": sources, "files": sorted(file_map.values(), key=lambda item: item["path"]), "warnings": warnings, "policy": "Source roles preserved; answer and derived-annotation text excluded from diagnostic retrieval."}
        if result != old:
            archive_current(root)
            for relative, data in content.items():
                target = inside(root, "library/sources/" + relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                # All writes happen only after source closure validation and archival.
                if target.suffix.lower() == ".md":
                    atomic_write(target, data.decode("utf-8"))
                else:
                    target.write_bytes(data)
            write_json(library / "manifest.json", result)
        index = build_index(root)
    return {"sources": len(sources), "files": len(file_map), "warnings": warnings, "index": index}


def build_library(root, source=None, demo=False):
    if demo:
        source = Path(__file__).resolve().parents[2] / "examples/materials"
        selected = [source / "demo-textbook.md"]
    else:
        source = Path(source).resolve()
        selected = [p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in {".md", ".png", ".jpg", ".jpeg", ".webp", ".pdf"} and not any("备份" in v for v in p.relative_to(source).parts)]
        # Original snapshots may contain same-year, unrelated legacy answer files.
        selected = [p for p in selected if not ("初试答案" in p.name and re.search(r"202[56]", p.name))]
    if not selected:
        raise ExamError("empty_materials", "没有找到可导入资料")
    content, warnings = _freeze_files(source, selected)
    entries = []
    for path in selected:
        if path.suffix.lower() != ".md":
            continue
        relative = path.relative_to(source)
        info = source_info(path, relative)
        if demo:
            info.update(id="demo-book", title="自制演示教材（非法律资料）")
        entries.append({**info, "path": "library/sources/" + relative.as_posix(), "_relative": relative.as_posix(), "verification": "source_text_not_fully_proofread"})
    return _install(root, content, entries, warnings, replace=True)


def import_material(root, path, role="textbook", title=None, source_id=None, apply=False):
    path = Path(path).resolve()
    if role not in ROLES - {"exam", "answers"}:
        raise ExamError("invalid_role", "教材导入支持 textbook、lecture、bilingual_notes、guide、usage_note；题集请走题库导入")
    if path.suffix.lower() not in {".md", ".txt"}:
        raise ExamError("requires_conversion", "先用 MinerU 转换为 Markdown，再导入")
    text = path.read_text(encoding="utf-8-sig")
    key = source_id or "material-" + digest(path.name + "\n" + text)[:16]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", key):
        raise ExamError("invalid_id", "资料ID应为小写字母、数字和短横线")
    relative = key + "/" + path.with_suffix(".md").name
    frozen, warnings = _freeze_files(path.parent, [path]) if path.suffix.lower() == ".md" else ({path.name: text.encode("utf-8")}, [])
    content = {key + "/" + name: value for name, value in frozen.items()}
    if path.suffix.lower() == ".txt":
        content = {relative: text.encode("utf-8")}
    entry = {"id": key, "title": title or path.stem, "role": role, "path": "library/sources/" + relative, "_relative": relative, "verification": "user_import_unverified"}
    preview = {"id": key, "role": role, "title": entry["title"], "files": len(content), "warnings": warnings, "applied": False}
    if apply:
        preview.update(_install(root, content, [entry], warnings), applied=True)
    return preview
