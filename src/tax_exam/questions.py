"""Multi-source question banks with answer isolation and conservative import."""
from pathlib import Path
import re
import unicodedata

from .common import ExamError, digest, inside, load_json, lock, write_json
from .library import checked_source, manifest

SOURCE_TYPES = {"past_exam", "textbook", "mock", "custom", "ai_generated"}
KINDS = {"名词解释", "简答", "论述", "案例", "计算", "选择", "其他"}
ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def normalized(text):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text).lower())


def kind_of(label):
    return next((kind for kind in KINDS if kind != "其他" and kind in label), "其他")


def parse_exam(text, year, source_id):
    """Read the two observed local Markdown layouts without inferring absent items."""
    result = []
    subject = "未标明"
    h2s = list(re.finditer(r"^## (.+)$", text, re.M))
    for idx, match in enumerate(h2s):
        label = match[1]
        section = text[match.end():h2s[idx + 1].start() if idx + 1 < len(h2s) else len(text)]
        section = section.split("\n---", 1)[0]
        if any(x in label for x in ["附录", "缺失题干说明"]):
            continue
        if "｜" in label:
            subject, type_label = label.split("｜", 1)
        elif label in ("中国税法学", "国际税法学", "法理学", "宪法学", "民法学", "刑法学"):
            subject, type_label = label, ""
        else:
            type_label = label
        # Original layout: ### 第1题：题干, with optional common context before it.
        explicit = list(re.finditer(r"^### 第(\d+)题[：:]\s*(.+)$", section, re.M))
        if explicit:
            context = section[:explicit[0].start()].strip()
            for n, question in enumerate(explicit):
                body = section[question.end():explicit[n + 1].start() if n + 1 < len(explicit) else len(section)].strip()
                result.append(_parsed(year, subject, type_label, question[1], question[2], body, context, source_id))
            continue
        # New layout: ## subject, ### type, numbered questions or a single essay.
        h3s = list(re.finditer(r"^### (.+)$", section, re.M))
        for n, heading in enumerate(h3s):
            label3 = heading[1]
            body = section[heading.end():h3s[n + 1].start() if n + 1 < len(h3s) else len(section)].strip()
            supplement = ""
            if kind_of(label3) == "案例":
                if "\n#### " in body:
                    body, supplement = body.split("\n#### ", 1)
                # In 2026, facts themselves are numbered; use the last explicit 问题 delimiter.
                split = re.split(r"\n问题[:：]?\s*\n", body)
                if len(split) > 1:
                    context, body = "\n问题\n".join(split[:-1]), split[-1]
                    points = list(re.finditer(r"^[（(](\d+)[）)]\s*(.+)$", body, re.M))
                else:
                    points = list(re.finditer(r"^[（(](\d+)[）)]\s*(.+)$", body, re.M))
                    context = body[:points[0].start()].strip() if points else ""
                if supplement:
                    context += "\n\n#### " + supplement
            else:
                points = list(re.finditer(r"^(\d+)\.\s+(.+)$", body, re.M))
                context = body[:points[0].start()].strip() if points else ""
            if points:
                for j, point in enumerate(points):
                    stem = body[point.start():points[j + 1].start() if j + 1 < len(points) else len(body)].strip()
                    stem = re.sub(r"^(?:\d+\.|[（(]\d+[）)])\s*", "", stem)
                    result.append(_parsed(year, subject, label3, point[1], stem, "", context, source_id))
            elif body:
                result.append(_parsed(year, subject, label3, "1", body, "", "", source_id))
    return result


def _parsed(year, subject, label, number, stem, body, context, source_id):
    key = f"{source_id}:{subject}:{label}:{number}"
    warnings = []
    missing = re.search(r"缺失|未显示|未提供|没有给出|未能辨认|被遮挡", context + label)
    partial = bool(missing and (kind_of(label) == "案例" or re.search(r"缺失|未显示|未能辨认|被遮挡", stem)))
    if missing:
        warnings.append("来源中存在缺失或未提供的信息，须核查")
    if "回忆" in label:
        warnings.append("考生回忆版，未经官方核验")
    return {
        "id": "q-" + digest(key)[:18], "year": year, "subject": subject.strip(),
        "kind": kind_of(label), "section": label, "number": str(number),
        "stem": stem.strip(), "context": context, "_body": body,
        "source_id": source_id, "completeness": "partial" if partial else "complete",
        "warnings": warnings, "verification": "unverified_source_transcription",
        "knowledge_points": [],
    }


def built_in_banks(root):
    data = manifest(root)
    sources = data["sources"]
    answer_sources = {s.get("year"): s for s in sources if s["role"] == "answers"}
    banks = []
    for source in sources:
        if source["role"] != "exam":
            continue
        text = checked_source(root, source).read_text(encoding="utf-8-sig")
        questions = parse_exam(text, source["year"], source["id"])
        answers = {}
        answer_source = answer_sources.get(source["year"])
        if answer_source:
            answer_text = checked_source(root, answer_source).read_text(encoding="utf-8-sig")
            for item in parse_exam(answer_text, source["year"], answer_source["id"]):
                answers[(item["subject"], item["section"], item["number"], normalized(item["stem"]))] = item
        for item in questions:
            item.pop("_body")
            item["source_path"] = source["path"]
            item["source_hash"] = source["sha256"]
            item["source_type"] = "past_exam"
            answer = answers.get((item["subject"], item["section"], item["number"], normalized(item["stem"])))
            if answer and answer["_body"]:
                item["answer"] = {"text": answer["_body"], "status": "source_reference_not_official", "source_path": answer_source["path"], "source_hash": answer_source["sha256"]}
            else:
                item["answer"] = None
        banks.append({"schema_version": 1, "id": "xmu-" + str(source["year"]), "name": source["title"], "version": source["sha256"][:12], "source_type": "past_exam", "questions": questions})
    return banks


def all_banks(root):
    banks = built_in_banks(root)
    from .recitation import question_banks
    from .selftests import sets
    banks.extend(question_banks(root))
    banks.extend(sets(root))
    folder = inside(root, "userdata/imported-banks")
    if folder.exists():
        for path in sorted(folder.glob("*.json")):
            bank = validate_bank(load_json(path))
            banks.append(bank)
    ids = [bank["id"] for bank in banks]
    if len(ids) != len(set(ids)):
        raise ExamError("bank_collision", "题库 ID 冲突；请为新增题库选择独立 ID")
    return banks


def validate_bank(data):
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ExamError("invalid_bank", "题库必须使用 schema_version: 1")
    if not isinstance(data.get("id"), str) or not ID.fullmatch(data["id"]):
        raise ExamError("invalid_bank", "题库 id 应为小写字母、数字、短横线或下划线")
    if not isinstance(data.get("name"), str) or not data["name"].strip() or data.get("source_type") not in SOURCE_TYPES:
        raise ExamError("invalid_bank", "题库缺少名称或合法来源类型")
    if not isinstance(data.get("version"), str) or not data["version"].strip():
        raise ExamError("invalid_bank", "题库必须有字符串 version")
    questions = data.get("questions")
    if not isinstance(questions, list) or not 1 <= len(questions) <= 10000:
        raise ExamError("invalid_bank", "每个题库应包含 1—10000 道题")
    ids = set()
    for item in questions:
        if not isinstance(item, dict):
            raise ExamError("invalid_bank", "题目必须为对象")
        for key in ("id", "stem", "subject"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ExamError("invalid_bank", "每道题必须有 id、stem 和 subject")
        if not ID.fullmatch(item["id"]) or item["id"] in ids:
            raise ExamError("invalid_bank", "题目 ID 无效或重复")
        ids.add(item["id"])
        if item.get("kind") not in KINDS:
            raise ExamError("invalid_bank", "题型不受支持")
        if item.get("completeness", "complete") not in ("complete", "partial"):
            raise ExamError("invalid_bank", "completeness 只能为 complete 或 partial")
        if data["source_type"] == "ai_generated" and not item.get("evidence"):
            raise ExamError("invalid_bank", "AI 自拟题必须附教材 evidence，不能伪称真题")
        if "year" in item and (type(item["year"]) is not int or not 1900 <= item["year"] <= 2200):
            raise ExamError("invalid_bank", "年份应为真实整数；未知时省略")
        if data["source_type"] == "ai_generated" and "year" in item:
            raise ExamError("invalid_bank", "AI 自拟题不使用考试年份")
        if not isinstance(item.get("context", ""), str) or not isinstance(item.get("knowledge_points", []), list):
            raise ExamError("invalid_bank", "context 应为文本，knowledge_points 应为列表")
        answer = item.get("answer")
        if answer is not None and (not isinstance(answer, dict) or not isinstance(answer.get("text"), str) or not answer.get("status")):
            raise ExamError("invalid_bank", "answer 应为 null 或含 text、status 的对象")
    return data


def import_bank(root, path, apply=False):
    data = validate_bank(path if isinstance(path, dict) else load_json(path))
    if any(q.get("practice_kind") in {"recitation", "daily_self_test"} or q.get("card_refs") for q in data["questions"]):
        raise ExamError("reserved_practice_metadata", "背诵卡和每日自测请使用card-save/self-test import，不能绕过已背范围校验")
    existing = all_banks(root)
    if any(bank["id"] == data["id"] for bank in existing):
        raise ExamError("bank_exists", "题库 ID 已存在；V1 不覆盖更新，请使用新的版本 ID 保留历史作答")
    from .library import read_block
    for question in data["questions"]:
        if data["source_type"] == "ai_generated":
            for evidence in question["evidence"]:
                read_block(root, evidence["block_id"], evidence["quote"])
    fingerprints = {normalized(q["stem"] + q.get("context", "")) for bank in existing for q in bank["questions"]}
    duplicates = [q["id"] for q in data["questions"] if normalized(q["stem"] + q.get("context", "")) in fingerprints]
    # Preview excludes answers to avoid polluting a diagnostic conversation.
    preview = {"bank_id": data["id"], "name": data["name"], "count": len(data["questions"]), "duplicates": duplicates, "applied": False}
    if apply:
        folder = inside(root, "userdata/imported-banks")
        with lock(folder / "import.lock"):
            target = folder / (data["id"] + ".json")
            if target.exists():
                raise ExamError("bank_exists", "题库已存在")
            write_json(target, data)
        preview["applied"] = True
    return preview


def import_markdown(root, path, bank_id, name, subject, source_type="custom", apply=False):
    text = Path(path).read_text(encoding="utf-8-sig")
    headers = list(re.finditer(r"^## ([a-z0-9][a-z0-9_-]{0,63})\s*\|\s*(.+)$", text, re.M))
    if not headers:
        raise ExamError("invalid_markdown", "题目标题应为 ## q1 | 简答；格式见 docs/question-banks.md")
    items = []
    for index, header in enumerate(headers):
        body = text[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(text)].strip()
        sections = list(re.finditer(r"^### (.+)$", body, re.M))
        parts = {"题干": body[:sections[0].start()].strip() if sections else body}
        for number, section in enumerate(sections):
            if section[1] not in {"题干", "共同案情", "参考答案"} or section[1] in parts and parts[section[1]]:
                raise ExamError("invalid_markdown", "小节只支持不重复的题干、共同案情、参考答案")
            parts[section[1]] = body[section.end():sections[number + 1].start() if number + 1 < len(sections) else len(body)].strip()
        items.append({"id": header[1], "stem": parts["题干"], "kind": header[2].strip(), "subject": subject, "context": parts.get("共同案情", ""), "completeness": "complete", "answer": {"text": parts["参考答案"], "status": "source_reference_not_official"} if parts.get("参考答案") else None})
    bank = {"schema_version": 1, "id": bank_id, "name": name, "subject": subject, "source_type": source_type, "version": digest(text)[:12], "questions": items}
    return import_bank(root, bank, apply)


def list_questions(root, bank_id=None, subject=None, kind=None, source_type=None, include_partial=False):
    result = []
    for bank in all_banks(root):
        if bank_id and bank["id"] != bank_id or source_type and bank["source_type"] != source_type:
            continue
        for question in bank["questions"]:
            if subject and subject not in question["subject"] or kind and kind != question["kind"]:
                continue
            if not include_partial and question.get("completeness", "complete") != "complete":
                continue
            result.append(public_question(bank, question))
    return result


def public_question(bank, item, include_answer=False):
    hidden = {"answer"} if include_answer else {"answer", "rubric", "evidence"}
    output = {key: value for key, value in item.items() if key not in hidden and not key.startswith("_")}
    usable_answer = item.get("answer")
    available = bool(isinstance(usable_answer, dict) and isinstance(usable_answer.get("text"), str) and usable_answer["text"].strip())
    output.update(bank_id=bank["id"], bank_version=bank["version"], source_type=bank["source_type"], id=bank["id"] + ":" + item["id"], has_reference_answer=available)
    if not include_answer and output.get("card_refs"):
        output["card_refs"] = [{"id": r["id"], "version": r["version"]} for r in output["card_refs"]]
    if include_answer:
        output["answer"] = item.get("answer")
    return output


def get_question(root, question_id, include_answer=False):
    for bank in all_banks(root):
        for item in bank["questions"]:
            if bank["id"] + ":" + item["id"] == question_id:
                output = public_question(bank, item, include_answer)
                if not output.get("card_refs"):
                    from .recitation import catalog, load
                    links = []
                    for key, version in catalog(root)["current"].items():
                        card = load(root, key, version, check=False)
                        if question_id in card["related_question_ids"]:
                            links.append({"id": key, "version": version})
                    if links:
                        output["learning_card_refs"] = links
                return output
    raise ExamError("unknown_question", "题目不存在，请先用 questions 查找完整 ID")


def bank_summary(root):
    return [{"id": bank["id"], "name": bank["name"], "version": bank["version"], "source_type": bank["source_type"], "questions": len(bank["questions"]), "with_reference": sum(bool(q.get("answer")) for q in bank["questions"]), "partial": sum(q.get("completeness") == "partial" for q in bank["questions"])} for bank in all_banks(root)]
