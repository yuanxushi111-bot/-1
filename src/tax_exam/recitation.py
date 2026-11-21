"""Immutable, source-checked lecture cards and journal-derived recall progress."""
from datetime import datetime, timedelta
import json
import re

from .common import ExamError, digest, file_hash, inside, load_json, local_now, lock, write_json, atomic_write
from . import markdown_store as md, study_settings
from .feedback import verify_evidence, text
from .library import manifest, checked_source, search

ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def catalog(root):
    path = inside(root, "library/recitation-manifest.json")
    return load_json(path) if path.exists() else {"schema_version": 1, "current": {}, "files": []}


def load(root, card_id, version=None, check=True):
    data = catalog(root)
    version = version or data["current"].get(card_id)
    entry = next((v for v in data["files"] if v["id"] == card_id and v["version"] == version), None)
    if not entry:
        raise ExamError("unknown_card", "背诵卡不存在，请先用cards查看")
    path = inside(root, entry["path"])
    if file_hash(path) != entry["sha256"]:
        raise ExamError("card_changed", "背诵卡被直接修改；请通过card-save生成新版本")
    card = md.read(path, "card")[-1]
    if card["id"] != card_id or card["version"] != version:
        raise ExamError("card_changed", "背诵卡标识与清单不一致")
    if check:
        current = next((s for s in manifest(root)["sources"] if s["id"] == card["source_id"]), None)
        if not current or current["sha256"] != card["source_hash"]:
            raise ExamError("card_source_changed", "讲义版本变化，先核对并更新卡片；旧记录和卡片版本保留")
        for item in card["points"]:
            verify_evidence(root, item["evidence"])
    return card


def metadata(card):
    return {key: card[key] for key in ("id", "version", "title", "subject", "priority", "learn_minutes", "source_id", "source_hash", "prerequisites", "known_limits", "related_question_ids")}


def save(root, payload, apply=False):
    if not isinstance(payload, dict) or not isinstance(payload.get("id"), str) or not ID.fullmatch(payload["id"]):
        raise ExamError("invalid_card", "卡片ID为1—40个小写字母、数字、短横线或下划线")
    source_id = payload.get("source_id", study_settings.get(root)["main_source_id"])
    source = next((s for s in manifest(root)["sources"] if s["id"] == source_id), None)
    if source_id != study_settings.get(root)["main_source_id"] or not source or source["role"] not in {"lecture", "textbook"}:
        raise ExamError("wrong_card_source", "背诵卡核心内容须来自配置的主讲义原文")
    points = payload.get("points")
    if not isinstance(points, list) or not 1 <= len(points) <= 20:
        raise ExamError("invalid_card", "背诵卡须有1—20个有原文依据的核心/补充要点")
    verified, ids = [], set()
    for point in points:
        if not isinstance(point, dict):
            raise ExamError("invalid_card", "每个要点须为对象")
        key = text(point.get("id"), "要点ID")
        if key in ids or not ID.fullmatch(key) or point.get("importance", "core") not in {"core", "supplement"}:
            raise ExamError("invalid_card", "要点ID重复/无效，或importance无效")
        ids.add(key)
        refs = verify_evidence(root, point.get("evidence", []))
        if not refs or any(v["source_id"] != source_id or v["source_hash"] != source["sha256"] or v.get("historical") for v in refs):
            raise ExamError("wrong_card_source", "每个卡片要点须有当前主讲义的原文证据")
        verified.append({"id": key, "description": text(point.get("description"), "要点内容"), "importance": point.get("importance", "core"), "evidence": refs})
    if not any(p["importance"] == "core" for p in verified):
        raise ExamError("invalid_card", "至少需要一个核心要点")
    outline = payload.get("memory_outline")
    if not isinstance(outline, list) or not outline or not all(isinstance(v, str) and v.strip() for v in outline):
        raise ExamError("invalid_card", "memory_outline须为非空提纲列表")
    minutes = payload.get("learn_minutes", 12)
    if type(minutes) is not int or not 3 <= minutes <= 60 or payload.get("priority", "A1") not in {"A1", "A2", "B"}:
        raise ExamError("invalid_card", "learn_minutes应为3—60分钟；优先级为A1/A2/B")
    prerequisites = payload.get("prerequisites", [])
    if not isinstance(prerequisites, list) or any(not isinstance(v, str) or not ID.fullmatch(v) or v == payload["id"] for v in prerequisites):
        raise ExamError("invalid_card", "前置卡片ID无效")
    for key in prerequisites:
        if key not in catalog(root)["current"]:
            raise ExamError("missing_prerequisite", "先建立前置卡片再引用")
    related = payload.get("related_question_ids", [])
    if not isinstance(related, list):
        raise ExamError("invalid_card", "related_question_ids应为列表")
    if related:
        from .questions import get_question
        for key in related:
            get_question(root, key)
    limits = payload.get("known_limits", [])
    if not isinstance(limits, list) or not all(isinstance(v, str) for v in limits):
        raise ExamError("invalid_card", "known_limits应为文本列表")
    card = {"schema_version": 1, "id": payload["id"], "title": text(payload.get("title"), "标题"), "subject": text(payload.get("subject"), "科目"), "body": text(payload.get("body"), "完整背诵正文"), "memory_outline": outline,
            "prompt": text(payload.get("prompt"), "闭卷抽查题"), "points": verified, "source_id": source_id, "source_hash": source["sha256"], "priority": payload.get("priority", "A1"), "learn_minutes": minutes,
            "prerequisites": prerequisites, "known_limits": limits, "related_question_ids": related, "status": "ai_lecture_reference_not_official"}
    card["version"] = digest(json.dumps(card, ensure_ascii=False, sort_keys=True))[:16]
    result = {**metadata(card), "applied": False, "core_points": sum(p["importance"] == "core" for p in verified)}
    if apply:
        with lock(inside(root, "library/recitation.lock")):
            data = catalog(root)
            path = f"library/recitation-cards/{card['id']}/{card['version']}.md"
            entry = next((v for v in data["files"] if v["path"] == path), None)
            if entry:
                load(root, card["id"], card["version"])
            else:
                atomic_write(inside(root, path), md.section("card", card, render(card)))
                data["files"].append({"id": card["id"], "version": card["version"], "path": path, "sha256": file_hash(inside(root, path))})
            data["current"][card["id"]] = card["version"]
            write_json(inside(root, "library/recitation-manifest.json"), data)
        result["applied"] = True
    return result


def render(card):
    lines = ["# " + card["title"], "", "AI依据主讲义整理的学习材料，非官方答案。", "", "## 完整背诵稿", card["body"], "", "## 记忆骨架"]
    lines += ["- " + item for item in card["memory_outline"]]
    lines += ["", "## 闭卷抽查题", card["prompt"], "", "## 原讲义依据"]
    for point in card["points"]:
        for ref in point["evidence"]:
            lines += [f"- {point['description']}：{ref['source_title']}；分册{ref.get('source_part') or '未标'}，PDF页序{ref['pdf_page_start']}—{ref['pdf_page_end']}，合并页序{ref.get('merged_page_start')}—{ref.get('merged_page_end')}；块{ref['block_id']}", "> " + ref["quote"].replace("\n", "\n> ")]
    if card["known_limits"]:
        lines += ["", "## 边界与待核实事项", *["- " + s for s in card["known_limits"]]]
    return "\n".join(lines)


def question_bank(card):
    key = "recite-" + card["id"] + "-" + card["version"][:8]
    return {"schema_version": 1, "id": key, "name": "讲义背诵抽查｜" + card["title"], "source_type": "ai_generated", "version": card["version"], "questions": [{
        "id": "recall", "subject": card["subject"], "kind": "简答", "stem": card["prompt"], "context": "", "practice_kind": "recitation", "completeness": "complete",
        "card_refs": [{"id": card["id"], "version": card["version"], "point_ids": [p["id"] for p in card["points"]]}],
        "knowledge_points": ["card:" + card["id"]], "rubric": {"version": card["version"], "items": card["points"]},
        "evidence": [ref for p in card["points"] for ref in p["evidence"]], "answer": {"text": card["body"], "status": "lecture_recitation_reference_not_official", "card_id": card["id"], "card_version": card["version"]}}]}


def question_banks(root):
    # Include archived card versions: old attempts continue to resolve their frozen question.
    return [question_bank(load(root, v["id"], v["version"], check=False)) for v in catalog(root)["files"]]


def progress(root, now=None):
    from .records import read_events, active_feedbacks, active_studies
    now = now or local_now()
    events = read_events(root)
    attempts = {e["id"]: e for e in events if e["kind"] == "attempt"}
    settings = study_settings.get(root)
    sources = {source["id"]: source for source in manifest(root)["sources"]}
    source_checks = {}
    output = []
    for key, version in sorted(catalog(root)["current"].items()):
        card = load(root, key, version, check=False)
        core = {p["id"] for p in card["points"] if p["importance"] == "core"}
        state = {**metadata(card), "status": "未学习", "next_review": None, "independent_pass_days": [], "unmeasured_points": sorted(core), "due": False, "error_count": 0}
        studies = [e for e in active_studies(events) if e.get("card_id") == key and e.get("card_version") == version and e.get("action") == "learned"]
        last_date, bad_date, covered = None, None, {}
        if studies:
            last_date = studies[-1]["local_date"]
            state.update(status="已学习", next_review=(datetime.fromisoformat(studies[-1]["timestamp"]).date() + timedelta(days=settings["review_intervals"][0])).isoformat())
        feedbacks = sorted(active_feedbacks(events), key=lambda e: attempts[e["target_id"]]["timestamp"])
        for feedback in feedbacks:
            attempt = attempts[feedback["target_id"]]
            snapshot = attempt["question_snapshot"]
            refs = [r for r in snapshot.get("card_refs", []) if r["id"] == key and r["version"] == version]
            if not refs:
                continue
            results = {r["point_id"]: r["status"] for r in feedback.get("point_results", [])}
            tested = set().union(*(set(r["point_ids"]) for r in refs)) & core
            if feedback["assessment"] == "unverified":
                state["status"] = "待核实"
                continue
            last_date = attempt["local_date"]
            state["next_review"] = feedback["next_review"]
            wrong = {p for p in tested if results.get(p) in {"missing", "partial", "incorrect"}}
            if wrong or attempt.get("hints_used") or attempt.get("answer_seen"):
                bad_date, covered = last_date, {}
                state.update(status="待复背", error_count=state["error_count"] + 1)
            else:
                covered.setdefault(last_date, set()).update(p for p in tested if results.get(p) == "covered")
                state["status"] = "复测中"
        passed = sorted(day for day, points in covered.items() if core <= points and (not bad_date or day > bad_date))
        state["independent_pass_days"] = passed
        state["unmeasured_points"] = sorted(core - set().union(*covered.values())) if covered else sorted(core)
        if len(passed) >= 2 and state["status"] != "待核实":
            state["status"] = "已巩固"
        try:
            source = sources.get(card["source_id"])
            if not source or source["sha256"] != card["source_hash"]:
                raise ExamError("card_source_changed", "讲义版本变化，请核对卡片版本")
            if source["id"] not in source_checks:
                try:
                    checked_source(root, source)
                    source_checks[source["id"]] = None
                except ExamError as error:
                    source_checks[source["id"]] = str(error)
            if source_checks[source["id"]]:
                raise ExamError("card_source_changed", source_checks[source["id"]])
        except ExamError as error:
            state.update(status="待核实", warning=str(error))
        state["due"] = bool(state["next_review"] and state["next_review"] <= now.date().isoformat() and state["status"] != "待核实")
        output.append(state)
    return output


def view(root, card_id, learn=False, complete=False, now=None, request_id=None):
    from .records import save_event
    card = load(root, card_id)
    if not learn and not complete:
        return {**metadata(card), "question_id": question_bank(card)["id"] + ":recall"}
    action = "learned" if complete else "viewed"
    saved = save_event(root, {"kind": "study", "action": action, "card_id": card_id, "card_version": card["version"], **({"request_id": request_id} if request_id else {})}, now)
    return {"card": card, "rendered_card": render(card), "record": saved, "message": "自报学习完成，尚不代表独立抽查通过" if complete else "已记录正文展示；请展示完整背诵稿并保留出处"}


def candidates(root, query, limit=5):
    source_id = study_settings.get(root)["main_source_id"]
    result = search(root, query, limit=15, book=source_id)
    blocks = [b for b in result["results"] if b["source_id"] == source_id and len(b["text"].strip()) > 100]
    return {"results": blocks[:max(1, min(limit, 10))], "message": "候选原文需核对上下文、版本与完整性后再card-save；不自动将标题/论文观点当作核心卡"}
