"""Small versioned Markdown containers, preserving prose outside machine blocks."""
import json
import re
from .common import ExamError, atomic_write


def safe(value):
    return str(value).replace("<!--", "&lt;!--")


def section(kind, data, prose):
    return safe(prose) + "\n\n" + f"<!-- tax-exam-{kind}:v1 -->\n```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + f"\n```\n<!-- /tax-exam-{kind} -->\n"


def read(path, kind):
    if not path.exists():
        return []
    if path.is_symlink():
        raise ExamError("unsafe_path", "Markdown数据不能是符号链接")
    text = path.read_text(encoding="utf-8-sig")
    start, end = f"<!-- tax-exam-{kind}:v1 -->", f"<!-- /tax-exam-{kind} -->"
    matches = re.findall(r"^" + re.escape(start) + r"\n```json\n(.*?)\n```\n" + re.escape(end) + r"$", text, re.M | re.S)
    if len(matches) != text.count(start) or len(matches) != text.count(end) or not matches:
        raise ExamError("damaged_markdown", "Markdown结构块损坏，保留原文件后核对")
    values = [json.loads(value) for value in matches]
    if not all(isinstance(value, dict) for value in values):
        raise ExamError("damaged_markdown", "Markdown结构数据应为对象")
    return values


def append(path, kind, data, prose):
    if path.exists():
        read(path, kind)
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    atomic_write(path, original + "\n" + section(kind, data, prose))
