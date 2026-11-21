"""Versioned local materials, Chinese/English search, and exact citations."""
from pathlib import Path
import json
import re
import sqlite3

from .common import ExamError, digest, file_hash, inside, load_json, lock

PAGE = re.compile(r"<!-- page (\d+) of (\d+) -->")
PART = re.compile(r"<!-- source-part:(\d+); pdf-page:(\d+)/(\d+) -->")
EVIDENCE_ROLES = {"textbook", "lecture", "bilingual_notes"}


def indexable(source):
    return source["role"] in EVIDENCE_ROLES | {"guide"} and not source.get("derived_from")
ALIASES = {
    "foreign tax credit": "外国税收抵免 抵免法",
    "tax credit": "税收抵免 抵免法",
    "permanent establishment": "常设机构",
    "treaty shopping": "税收协定滥用 协定购物",
    "principal purpose test": "主要目的测试 协定反滥用",
    "principle purpose test": "主要目的测试 协定反滥用",
    "transfer pricing": "转让定价 转移定价",
    "double taxation": "重复征税 双重征税",
    "税收抵免法": "外国税收抵免 抵免法",
}


def terms(text):
    words = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text.lower())
    result = []
    for word in words:
        if re.fullmatch(r"[\u3400-\u9fff]+", word):
            result.extend(word[i:i + 2] for i in range(max(1, len(word) - 1)))
        else:
            result.append(word)
    return result


def expanded(text):
    lower = text.lower()
    return text + " " + " ".join(value for key, value in ALIASES.items() if key in lower)


def manifest(root):
    path = Path(root) / "library/manifest.json"
    if not path.exists():
        raise ExamError("no_library", "尚无资料；请运行 build_library.py 导入，或使用包含资料的私人包")
    data = load_json(path)
    if data.get("schema_version") != 1:
        raise ExamError("unsupported_schema", "不支持的资料清单版本")
    return data


def checked_source(root, source):
    path = inside(root, source["path"])
    if not path.is_file() or file_hash(path) != source["sha256"]:
        raise ExamError("source_changed", f"资料已变更或丢失：{source['title']}；请重新导入并重建索引")
    return path


def chunks(text, source, target=1500):
    """Offsets refer to untouched source text, including cross-page paragraphs."""
    page, total, heading = None, None, []
    part, merged = None, 0
    first_merged, last_merged, chunk_part = None, None, None
    start, end, first_page, last_page, chunk_heading = None, 0, None, None, ""
    offset = 0

    def result():
        body = text[start:end]
        return {
            "id": "b-" + digest(source["id"] + source["sha256"] + str(start) + ":" + str(end))[:20],
            "source_id": source["id"], "source_hash": source["sha256"],
            "path": source["path"], "title": source["title"], "role": source["role"],
            "heading": chunk_heading, "start": start, "end": end,
            "line_start": text.count("\n", 0, start) + 1,
            "line_end": text.count("\n", 0, max(start, end - 1)) + 1,
            "pdf_page_start": first_page, "pdf_page_end": last_page,
            "source_part": chunk_part, "source_pdf_page_start": first_page, "source_pdf_page_end": last_page,
            "merged_page_start": first_merged, "merged_page_end": last_merged,
            "page_anchor": f"textbook-page-{first_merged}" if first_merged and f"^textbook-page-{first_merged}" in text else None,
            "text": body,
        }

    for paragraph in re.findall(r"[^\n]+(?:\n(?!\n)[^\n]+)*\n*|\n+", text):
        p_start, p_end = offset, offset + len(paragraph)
        offset = p_end
        match_page = PAGE.search(paragraph)
        match_part = PART.search(paragraph)
        header = re.match(r"^(#{1,6})\s+(.+)", paragraph)
        if start is not None and (header or end - start + len(paragraph) > target or match_part and int(match_part[1]) != part):
            yield result()
            start = None
        if match_page:
            page, total = int(match_page[1]), int(match_page[2])
            merged += 1
        if match_part:
            part = int(match_part[1])
        if header:
            depth = len(header[1])
            # OCR heading levels are inconsistent; do not invent a chapter ancestry.
            heading = [header[2].splitlines()[0]]
        if not paragraph.strip():
            continue
        if start is None:
            start, first_page, chunk_heading = p_start, page, " / ".join(heading[-4:])
            first_merged, chunk_part = merged or None, part
        end, last_page = p_end, page
        last_merged = merged or None
    if start is not None:
        yield result()


def build_index(root):
    root = Path(root)
    data = manifest(root)
    folder = inside(root, "indexes")
    folder.mkdir(parents=True, exist_ok=True)
    with lock(folder / "build.lock"):
        temp = folder / "materials.build.sqlite"
        temp.unlink(missing_ok=True)
        conn = sqlite3.connect(temp)
        try:
            conn.executescript("""
                CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE blocks(id TEXT PRIMARY KEY, payload TEXT);
                CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED,tokens);
            """)
            count = 0
            for source in data["sources"]:
                if not indexable(source):
                    continue  # Keep reference answers and annotated guides out of diagnostic search.
                text = checked_source(root, source).read_text(encoding="utf-8-sig")
                for block in chunks(text, source):
                    conn.execute("INSERT INTO blocks VALUES (?,?)", (block["id"], json.dumps(block, ensure_ascii=False)))
                    tokens = terms(block["heading"] * 3 + " " + block["text"])
                    conn.execute("INSERT INTO search VALUES (?,?)", (block["id"], " ".join(tokens)))
                    count += 1
            conn.execute("INSERT INTO meta VALUES ('manifest_hash',?)", (file_hash(root / "library/manifest.json"),))
            conn.commit()
        finally:
            conn.close()
        temp.replace(folder / "materials.sqlite")
    return {"blocks": count, "sources": len([s for s in data["sources"] if indexable(s)])}


def open_index(root):
    root = Path(root)
    data = manifest(root)
    for source in data["sources"]:
        if indexable(source):
            checked_source(root, source)
    db = root / "indexes/materials.sqlite"
    if not db.exists():
        raise ExamError("no_index", "请先执行 index 构建教材索引")
    conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    row = conn.execute("SELECT value FROM meta WHERE key='manifest_hash'").fetchone()
    if not row or row[0] != file_hash(root / "library/manifest.json"):
        conn.close()
        raise ExamError("stale_index", "资料清单与索引版本不同，请重建索引")
    return conn


def search(root, query, limit=5, book=None, role=None):
    if not query.strip() or len(query) > 1000:
        raise ExamError("invalid_query", "查询应为 1—1000 个字符")
    original = query.strip()
    query = expanded(original)
    tokens = list(dict.fromkeys(terms(query)))[:80]
    if not tokens:
        return {"results": [], "status": "no_evidence"}
    conn = open_index(root)
    try:
        expression = " OR ".join('"' + token.replace('"', '') + '"' for token in tokens)
        rows = conn.execute("SELECT id,bm25(search) FROM search WHERE search MATCH ? ORDER BY bm25(search) LIMIT 500", (expression,)).fetchall()
        candidates = []
        for block_id, rank in rows:
            block = json.loads(conn.execute("SELECT payload FROM blocks WHERE id=?", (block_id,)).fetchone()[0])
            if role and block["role"] != role or not role and block["role"] not in EVIDENCE_ROLES:
                continue
            if book and book.lower() not in (block["title"] + " " + block["source_id"]).lower():
                continue
            score = -rank + (15 if original.lower() in block["text"].lower() else 0) + (8 if original.lower() in block["heading"].lower() else 0)
            block["retrieval_score"] = round(score, 5)
            candidates.append(block)
        candidates.sort(key=lambda item: item["retrieval_score"], reverse=True)
        return {"query": original, "status": "candidates_require_verification" if candidates else "no_evidence", "results": candidates[:max(1, min(limit, 15))]}
    finally:
        conn.close()


def verify_cached_block(root, block, data):
    source = next((source for source in data["sources"] if source["id"] == block["source_id"]), None)
    if not source or any(block[key] != source[field] for key, field in (("source_hash", "sha256"), ("path", "path"), ("role", "role"), ("title", "title"))):
        raise ExamError("cached_block_changed", "引用块元数据与资料清单不一致，请重建索引")
    content = checked_source(root, source).read_text(encoding="utf-8-sig")
    expected_id = "b-" + digest(source["id"] + source["sha256"] + str(block["start"]) + ":" + str(block["end"]))[:20]
    if content[block["start"]:block["end"]] != block["text"] or block["id"] != expected_id:
        raise ExamError("cached_block_changed", "引用块与原始文件不一致，请重建索引")


def read_block(root, block_id, quote=None):
    conn = open_index(root)
    try:
        row = conn.execute("SELECT payload FROM blocks WHERE id=?", (block_id,)).fetchone()
        block = json.loads(row[0]) if row else None
        if block is not None:
            verify_cached_block(root, block, manifest(root))
        if block is None:
            for archive in sorted((Path(root) / "library/history").glob("*/manifest.json")):
                database = archive.parent / "materials.sqlite"
                if not database.exists():
                    continue
                historic = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
                try:
                    old = historic.execute("SELECT payload FROM blocks WHERE id=?", (block_id,)).fetchone()
                finally:
                    historic.close()
                if old:
                    block = json.loads(old[0])
                    verify_cached_block(archive.parent, block, load_json(archive))
                    path = inside(archive.parent, block["path"])
                    if file_hash(path) != block["source_hash"]:
                        raise ExamError("archive_changed", "历史引用资料校验失败")
                    block["original_path"] = block["path"]
                    block["path"] = path.relative_to(Path(root).resolve()).as_posix()
                    block["historical"] = True
                    break
        if block is None:
            raise ExamError("unknown_block", "引用块不存在，当前与归档资料均未找到")
        if quote is not None:
            if not quote.strip() or quote not in block["text"]:
                raise ExamError("quote_mismatch", "引文不在该原文块中")
            block["quote_verified"] = True
        return block
    finally:
        conn.close()
