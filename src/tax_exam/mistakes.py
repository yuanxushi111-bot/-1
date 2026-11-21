"""Automatic, rebuildable Markdown mistake book derived from dated event journals."""
from datetime import date, datetime
from pathlib import Path

from .common import ExamError, atomic_write, file_hash, inside, load_json, local_now, lock, write_json

MARKER = "<!-- tax-exam-mistake-view:v1 -->"


def project(root):
    from .records import read_events, active_feedbacks
    from .questions import get_question
    events = read_events(root)
    attempts = {event["id"]: event for event in events if event["kind"] == "attempt"}
    grouped = {}
    ordered = sorted(active_feedbacks(events), key=lambda event: datetime.fromisoformat(attempts.get(event["target_id"], event)["timestamp"]))
    for feedback in ordered:
        attempt = attempts.get(feedback["target_id"])
        if attempt is None or feedback.get("mistake_opt_out"):
            continue
        question_id = feedback["question_id"]
        if question_id not in grouped:
            grouped[question_id] = {"question_id": question_id, "question": attempt.get("question_snapshot", {}), "history": [], "error_count": 0, "status": None, "pass_days": set(), "last_bad_date": None, "required_points": set()}
        item = grouped[question_id]
        if feedback["assessment"] in {"needs_work", "hinted"}:
            item["error_count"] += 1
            item["status"] = "待复习"
            item["pass_days"] = set()
            item["last_bad_date"] = attempt["local_date"]
            item["required_points"].update(point["point_id"] for point in feedback.get("mistake_reasons", []) if point.get("point_id"))
        elif feedback["assessment"] == "unverified":
            item["status"] = "待核实"
        elif item["status"]:
            results = {point["point_id"]: point["status"] for point in feedback.get("point_results", [])}
            points_verified = all(results.get(key) == "covered" for key in item["required_points"])
            if item["required_points"] and not results:
                points_verified = False
            if points_verified and not attempt.get("hints_used") and not attempt.get("answer_seen") and attempt["local_date"] > (item["last_bad_date"] or ""):
                item["pass_days"].add(attempt["local_date"])
                item["status"] = "已巩固" if len(item["pass_days"]) >= 2 else "复测中"
        # Keep successful first attempts out of the mistake book.
        if item["status"]:
            item["history"].append({"attempt": attempt, "feedback": feedback})
            item["next_review"] = feedback.get("next_review")
    result = []
    for item in grouped.values():
        if not item["status"]:
            continue
        try:
            question = get_question(root, item["question_id"])
            if item["question"].get("card_refs"):
                from .recitation import load
                for ref in item["question"]["card_refs"]:
                    load(root, ref["id"], ref["version"])
                    from .recitation import catalog
                    if catalog(root)["current"].get(ref["id"]) != ref["version"]:
                        item.update(status="待核实", warning="背诵卡已有新版本，原作答与错因保留，需核对要点对应关系")
            if item["question"].get("bank_version") != question["bank_version"]:
                item["status"] = "待核实"
                item["warning"] = "题库版本变化，保留旧题快照，需复核对应关系"
        except ExamError as error:
            item["status"] = "待核实"
            item["warning"] = "原题/卡片需核对，保留历史快照：" + str(error)
        item["independent_pass_days"] = sorted(item.pop("pass_days"))
        item["required_points"] = sorted(item["required_points"])
        result.append(item)
    return sorted(result, key=lambda item: (item["status"] == "已巩固", item.get("next_review") or "9999", -item["error_count"], item["question_id"]))


def list_mistakes(root, status=None, subject=None, due=False, details=False, on=None):
    today = date.fromisoformat(on) if on else local_now().date()
    result = []
    for item in project(root):
        question = item["question"]
        if status and item["status"] != status or subject and subject not in question.get("subject", ""):
            continue
        is_due = bool(item.get("next_review") and date.fromisoformat(item["next_review"]) <= today and item["status"] not in {"已巩固", "待核实"})
        if due and not is_due:
            continue
        if details:
            result.append({**item, "due": is_due})
        else:
            # No old student answers, reference answers, or feedback in drill listings.
            result.append({"question_id": item["question_id"], "stem": question.get("stem"), "context": question.get("context", ""), "subject": question.get("subject"), "status": item["status"], "error_count": item["error_count"], "next_review": item.get("next_review"), "due": is_due})
    return result


def rebuild(root):
    from .records import _quote
    from .feedback import format_feedback
    folder = inside(root, "userdata/mistake-book")
    with lock(folder / "write.lock"):
        items = project(root)
        pages = {}
        index = [MARKER, "# 自动错题索引", "", "由日期学习日志重建。个人笔记请写入 study-records。", "", "| 题目 | 状态 | 有效错误次数 | 下次复测 |", "| --- | --- | ---: | --- |"]
        for item in items:
            title = item["question"].get("stem", item["question_id"]).replace("|", "／").replace("\n", " ")
            index.append(f"| {title} | {item['status']} | {item['error_count']} | {item.get('next_review') or '待安排'} |")
            for pair in item["history"]:
                attempt, feedback = pair["attempt"], pair["feedback"]
                day = attempt["local_date"]
                lines = pages.setdefault(day + ".md", [MARKER, f"# {day} 错题与复测记录", "", "自动生成；原始作答和个人笔记保留在同日学习日志。", ""])
                lines += ["## " + title, f"题目ID：{item['question_id']}；当前状态：{item['status']}", "", "### 原题与共同案情", _quote(item["question"].get("stem", "")), _quote(item["question"].get("context", "")), "", "### 我的原始回答", _quote(attempt["answer"]), "", f"原始记录：../study-records/{attempt['local_date']}.md；事件：{attempt['id']}", ""]
                if feedback.get("feedback_format") == 2:
                    lines.append(format_feedback(feedback))
                else:
                    lines += ["### V1.0反馈", _quote(feedback.get("feedback", "")), "参考答案和细分错因未在旧日志保存，不补造历史内容。"]
        desired = {name: "\n".join(lines) + "\n" for name, lines in pages.items()}
        desired["错题索引.md"] = "\n".join(index) + "\n"
        state_file = folder / "view-manifest.json"
        old = load_json(state_file) if state_file.exists() else {"files": []}
        # Detect hand edits before rewriting a derived page; never silently lose them.
        for entry in old["files"]:
            file = inside(folder, entry["path"])
            if file.exists() and file_hash(file) != entry["sha256"]:
                raise ExamError("mistake_view_edited", "错题视图有手工修改，请先转存到日期学习日志再重建")
        old_names = {entry["path"] for entry in old["files"]}
        for name, content in desired.items():
            target = inside(folder, name)
            if target.exists() and name not in old_names:
                raise ExamError("unmanaged_mistake_file", "同名错题文件不是当前工具维护，拒绝覆盖")
        for name, content in desired.items():
            atomic_write(inside(folder, name), content)
        for name in old_names - set(desired):
            file = inside(folder, name)
            if file.is_file() and file.read_text(encoding="utf-8").startswith(MARKER):
                file.unlink()
        write_json(state_file, {"schema_version": 1, "files": [{"path": name, "sha256": file_hash(inside(folder, name))} for name in sorted(desired)]})
    return {"items": len(items), "pages": len(pages), "index": "userdata/mistake-book/错题索引.md"}
