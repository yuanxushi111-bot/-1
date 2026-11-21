"""Append-only dated Markdown journals; review state is rebuilt from these files."""
from datetime import date, datetime, timedelta
from pathlib import Path
import json
import re
import uuid

from .common import ExamError, atomic_write, digest, inside, local_now, lock
from .library import read_block
from .questions import get_question

START = "<!-- tax-exam-event:v1 -->"
END = "<!-- /tax-exam-event -->"
PATTERN = re.compile(r"^" + re.escape(START) + r"\n```json\n(.*?)\n```\n" + re.escape(END) + r"$", re.M | re.S)
ASSESSMENTS = {"needs_work", "hinted", "independent", "unverified"}


def day(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ExamError("invalid_date", "日期必须为 YYYY-MM-DD")


def folder(root):
    return inside(root, "userdata/study-records")


def read_events(root, on=None):
    files = [folder(root) / (day(on).isoformat() + ".md")] if on else sorted(folder(root).glob("????-??-??.md"))
    events, seen = [], set()
    for path in files:
        if not path.exists():
            continue
        if path.is_symlink():
            raise ExamError("unsafe_path", "学习记录不应链接到项目外")
        text = path.read_text(encoding="utf-8-sig")
        matches = list(PATTERN.finditer(text))
        if text.count(START) != len(matches) or text.count(END) != len(matches):
            raise ExamError("damaged_record", f"{path.name} 的结构化记录标记损坏；保留文件并人工核对后重试")
        for match in matches:
            try:
                event = json.loads(match[1])
                if event.get("schema_version") != 1 or not isinstance(event.get("id"), str) or event["kind"] not in {"attempt", "feedback", "note", "cancel", "study"}:
                    raise ValueError("不支持的记录")
                if event["id"] in seen:
                    raise ValueError("重复记录 ID")
                # A human edit must not silently move an event to a different day.
                if day(event["local_date"]).isoformat() != path.stem:
                    raise ValueError("记录日期与文件名不同")
                timestamp = datetime.fromisoformat(event["timestamp"])
                if timestamp.tzinfo is None:
                    raise ValueError("记录时间缺少时区")
                seen.add(event["id"])
            except (ValueError, TypeError, KeyError) as error:
                raise ExamError("damaged_record", f"{path.name} 中有无法读取的记录：{error}")
            events.append(event)
    return sorted(events, key=lambda event: datetime.fromisoformat(event["timestamp"]))


def active_feedbacks(events):
    cancelled = {event["target_id"] for event in events if event["kind"] == "cancel"}
    latest = {}
    for event in events:
        if event["kind"] == "feedback" and event["id"] not in cancelled:
            latest[event["target_id"]] = event
    return sorted(latest.values(), key=lambda event: datetime.fromisoformat(event["timestamp"]))


def active_studies(events):
    cancelled = {event["target_id"] for event in events if event["kind"] == "cancel"}
    return [event for event in events if event["kind"] == "study" and event["id"] not in cancelled]


def review_state(root, on=None):
    today = day(on) if on else local_now().date()
    events = read_events(root)
    latest = {}
    dates = {}
    for event in active_feedbacks(events):
        if event.get("card_refs"):
            continue  # Card-level coverage is projected separately; one subquestion is not a whole card.
        if event["assessment"] == "unverified":
            continue
        for key in event["review_keys"]:
            if event["assessment"] == "independent":
                dates.setdefault(key, set()).add(event["local_date"])
            elif event["assessment"] == "needs_work":
                dates[key] = set()
            latest[key] = event
    states = []
    for key, event in latest.items():
        states.append({"key": key, "question_id": event["question_id"], "assessment": event["assessment"], "next_review": event["next_review"], "due": day(event["next_review"]) <= today, "independent_days": len(dates.get(key, set())), "last_event": event["id"], "status": "需补课" if event["assessment"] == "needs_work" else "提示后可答" if event["assessment"] == "hinted" else "独立可答（迁移能力仍需验证）"})
    from .recitation import progress, load, question_bank
    for card in progress(root):
        if card["next_review"] and card["status"] != "待核实":
            states.append({"key": "card:" + card["id"], "question_id": question_bank(load(root, card["id"]))["id"] + ":recall", "assessment": "needs_work" if card["status"] == "待复背" else "independent" if card["independent_pass_days"] else "hinted", "next_review": card["next_review"], "due": day(card["next_review"]) <= today, "independent_days": len(card["independent_pass_days"]), "status": card["status"], "unmeasured_points": card["unmeasured_points"]})
    return sorted(states, key=lambda state: (state["next_review"], state["key"]))


def _quote(value):
    # Human-readable content cannot inject another structured event delimiter.
    value = str(value).replace("<!--", "&lt;!--")
    return "\n".join("> " + line for line in value.splitlines()) or "> （空）"


def render_event(event):
    labels = {"attempt": "作答原文", "feedback": "讲解反馈与复测", "note": "个人笔记", "cancel": "取消一条反馈", "study": "学习任务记录（不等于独立通过）"}
    parts = [f"\n## {event['timestamp'][11:19]} · {labels[event['kind']]}\n", f"记录 ID：`{event['id']}`\n"]
    fields = [("question_id", "题目"), ("answer", "我的原始作答"), ("feedback", "AI 反馈（辅助判断）"), ("text", "个人笔记"), ("assessment", "作答状态"), ("next_review", "下次复测"), ("target_id", "关联记录"), ("action", "学习动作"), ("card_title", "背诵卡"), ("card_version", "卡片版本"), ("task_title", "计划任务")]
    if event.get("feedback_format") == 2:
        from .feedback import format_feedback
        parts.append("\n" + format_feedback(event))
        fields = []
    for key, label in fields:
        if key in event:
            parts.extend([f"\n### {label}\n", _quote(event[key]) + "\n"])
    if event.get("evidence"):
        parts.append("\n### 教材依据\n")
        for evidence in event["evidence"]:
            parts.append(_quote(f"{evidence['source_title']} | {evidence['path']} | PDF页序 {evidence['pdf_page_start']}—{evidence['pdf_page_end']} | {evidence['block_id']}\n{evidence['quote']}") + "\n")
    parts.append("\n<details><summary>结构化记录（用于恢复复习进度；个人笔记请写在此块外）</summary>\n\n")
    parts.append(START + "\n```json\n" + json.dumps(event, ensure_ascii=False, indent=2) + "\n```\n" + END + "\n\n</details>\n")
    return "".join(parts)


def update_mistake_book(root):
    from .mistakes import rebuild
    try:
        return {"updated": True, **rebuild(root)}
    except (ExamError, OSError, ValueError, KeyError, TypeError) as error:
        return {"updated": False, "warning": "原始日志已保存，错题视图未更新；可执行mistakes --rebuild重试", "error": str(error)}


def save_event(root, payload, now=None, allow_legacy=False):
    if not isinstance(payload, dict):
        raise ExamError("invalid_record", "记录必须为 JSON 对象")
    now = now or local_now()
    out = folder(root)
    with lock(out / "write.lock"):
        previous = read_events(root)
        request_id = payload.get("request_id")
        if request_id:
            if not isinstance(request_id, str) or len(request_id) > 128:
                raise ExamError("invalid_record", "request_id 应为不超过128字符的字符串")
            already = next((event for event in previous if event.get("request_id") == request_id), None)
            if already:
                if already.get("request_hash") != digest(json.dumps(payload, ensure_ascii=False, sort_keys=True)):
                    raise ExamError("request_conflict", "同一个 request_id 对应不同内容，请换用新的请求 ID")
                response = {"event": already, "duplicate_request": True, "path": f"userdata/study-records/{already['local_date']}.md", "mistake_book": update_mistake_book(root)}
                if already.get("feedback_format") == 2:
                    from .feedback import format_feedback
                    response["rendered_feedback"] = format_feedback(already)
                return response
        event = {"schema_version": 1, "id": "e-" + uuid.uuid4().hex, "timestamp": now.isoformat(), "local_date": now.date().isoformat(), "kind": payload.get("kind")}
        if request_id:
            event["request_id"] = request_id
            event["request_hash"] = digest(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        kind = event["kind"]
        if kind == "attempt":
            if not isinstance(payload.get("answer"), str) or not payload["answer"].strip():
                raise ExamError("invalid_record", "请保存真实作答；不会可明确填写‘不会’")
            if type(payload.get("hints_used", False)) is not bool:
                raise ExamError("invalid_record", "hints_used 应为布尔值")
            # The user has now answered. Keep target point IDs internally, without storing
            # the reference answer or rubric in the raw-attempt snapshot.
            full_question = get_question(root, payload.get("question_id"), True)
            question = {key: value for key, value in full_question.items() if key not in {"answer", "rubric", "evidence"}}
            if type(payload.get("answer_seen", False)) is not bool:
                raise ExamError("invalid_record", "answer_seen应为布尔值")
            exposed_today = any(item["kind"] == "feedback" and item.get("question_id") == question["id"] and item["local_date"] == event["local_date"] and item.get("reference_answer", {}).get("origin") in {"bank", "bank_with_supplement", "textbook_generated"} for item in previous)
            refs = question.get("card_refs", [])
            for ref in refs:
                from .recitation import load
                load(root, ref["id"], ref["version"])
            for ref in refs + question.get("learning_card_refs", []):
                exposed_today = exposed_today or any(item["local_date"] == event["local_date"] and (item["kind"] == "study" and item.get("action") in {"viewed", "learned"} and item.get("card_id") == ref["id"] and item.get("card_version") == ref["version"] or item["kind"] == "feedback" and any(r["id"] == ref["id"] and r["version"] == ref["version"] for r in item.get("card_refs", []))) for item in previous)
            event.update(question_id=question["id"], question_snapshot=question, answer=payload["answer"], hints_used=payload.get("hints_used", False), answer_seen=payload.get("answer_seen", False) or exposed_today)
        elif kind == "feedback":
            target = next((item for item in previous if item["id"] == payload.get("target_id") and item["kind"] == "attempt"), None)
            if target is None:
                raise ExamError("unknown_attempt", "先保存原始作答，再提交对应反馈")
            if "feedback" in payload and (not isinstance(payload["feedback"], str) or not payload["feedback"].strip()):
                raise ExamError("invalid_record", "feedback应为非空文本，或省略该补充字段")
            from .feedback import validate_feedback
            if allow_legacy and "rubric" not in payload:
                if payload.get("assessment") not in ASSESSMENTS - {"unverified"}:
                    raise ExamError("invalid_record", "旧反馈状态无效")
                validated = {"assessment": payload["assessment"]}
            else:
                validated = validate_feedback(root, payload, target)
                event.update(validated)
            assessment = validated["assessment"]
            if target["question_snapshot"].get("card_refs"):
                event.update(card_refs=target["question_snapshot"]["card_refs"], practice_kind=target["question_snapshot"].get("practice_kind"))
            if assessment == "independent" and (target["hints_used"] or target.get("answer_seen")):
                raise ExamError("hinted_attempt", "使用过提示的作答不能标为独立可答")
            evidence = validated.get("evidence", payload.get("evidence", []))
            if not isinstance(evidence, list) or not evidence and assessment != "unverified":
                raise ExamError("no_evidence", "教学反馈须附教材原文证据；无法核实时先保存 note")
            verified = []
            for item in evidence:
                block = read_block(root, item["block_id"], item["quote"])
                verified.append({"block_id": block["id"], "source_id": block["source_id"], "source_hash": block["source_hash"], "source_title": block["title"], "path": block["path"], "pdf_page_start": block["pdf_page_start"], "pdf_page_end": block["pdf_page_end"], "source_part": block.get("source_part"), "merged_page_start": block.get("merged_page_start"), "merged_page_end": block.get("merged_page_end"), "quote": item["quote"]})
            keys = target["question_snapshot"]["knowledge_points"] if target["question_snapshot"].get("card_refs") else payload.get("knowledge_points") or [target["question_id"]]
            if not isinstance(keys, list) or not all(isinstance(key, str) and key.strip() for key in keys):
                raise ExamError("invalid_record", "knowledge_points 应为非空知识点名称列表")
            # Multiple retries on the same day do not lengthen the review interval.
            prior_dates = {}
            for item in active_feedbacks(previous):
                if day(item["local_date"]) < now.date():
                    for key in item["review_keys"]:
                        if item["assessment"] in {"needs_work", "hinted"}:
                            prior_dates[key] = set()
                        elif item["assessment"] == "independent":
                            prior_dates.setdefault(key, set()).add(item["local_date"])
            successes = min((len(prior_dates.get(key, set())) for key in keys), default=0)
            from .study_settings import get
            intervals = get(root)["review_intervals"]
            if target["question_snapshot"].get("card_refs"):
                from .recitation import progress, load
                state_by_id = {s["id"]: s for s in progress(root, now)}
                counts, full = [], True
                for ref in target["question_snapshot"]["card_refs"]:
                    card = load(root, ref["id"], ref["version"])
                    core = {p["id"] for p in card["points"] if p["importance"] == "core"}
                    full = full and core <= set(ref["point_ids"])
                    counts.append(len(state_by_id.get(ref["id"], {}).get("independent_pass_days", [])))
                successes = min(counts, default=0) if full else 0
            interval = intervals[min(successes, len(intervals) - 1)] if assessment == "independent" else intervals[0]
            next_review = payload.get("next_review") or (now.date() + timedelta(days=interval)).isoformat()
            if day(next_review) < now.date():
                raise ExamError("invalid_date", "新安排的复测日期不能早于本机今日")
            event.update(question_id=target["question_id"], target_id=target["id"], assessment=assessment, feedback=payload.get("feedback", validated.get("verdict", "")), evidence=verified, review_keys=list(dict.fromkeys(keys)), next_review=next_review)
            event["mistake_opt_out"] = bool(payload.get("mistake_opt_out", False))
        elif kind == "study":
            from .daily import validate_study
            event.update(validate_study(root, payload, now))
        elif kind == "note":
            if not isinstance(payload.get("text"), str) or not payload["text"].strip():
                raise ExamError("invalid_record", "笔记内容不能为空")
            event["text"] = payload["text"]
        elif kind == "cancel":
            target = next((item for item in previous if item["id"] == payload.get("target_id") and item["kind"] in {"feedback", "study"}), None)
            if not target:
                raise ExamError("unknown_feedback", "只能取消已存在的反馈或学习状态记录")
            event.update(target_id=target["id"], text=payload.get("text", "用户取消这条反馈，保留历史原文"))
        else:
            raise ExamError("invalid_record", "kind 应为 attempt、feedback、note、cancel 或 study")
        path = out / (now.date().isoformat() + ".md")
        if path.is_symlink():
            raise ExamError("unsafe_path", "学习记录不能写入符号链接")
        original = path.read_text(encoding="utf-8") if path.exists() else f"---\nschema_version: 1\ndate: {now.date().isoformat()}\n---\n\n# {now.date().isoformat()} 学习记录\n"
        if path.exists():
            atomic_write(inside(root, "userdata/backups/" + path.name + ".previous"), original)
        atomic_write(path, original + render_event(event))
    result = {"event": event, "path": path.relative_to(root).as_posix(), "duplicate_request": False}
    if kind in {"feedback", "cancel"}:
        result["mistake_book"] = update_mistake_book(root)
    if event.get("feedback_format") == 2:
        from .feedback import format_feedback
        result["rendered_feedback"] = format_feedback(event)
    return result
