"""Today's studied scope, frozen questions/rubrics, answer-free drill views."""
import json
from .common import ExamError, digest, inside, local_now, lock
from . import markdown_store as md, recitation, study_settings


def sets(root, on=None):
    folder = inside(root, "userdata/daily-self-tests")
    files = [folder / (on + ".md")] if on else sorted(folder.glob("????-??-??.md"))
    result = []
    for file in files:
        for bank in md.read(file, "self-test"):
            if bank.get("schema_version") != 1 or bank.get("study_date") != file.stem:
                raise ExamError("damaged_self_test", "自测日期或格式与文件不一致")
            result.append(bank)
    return result


def studied_cards(root, now=None, include_due=False):
    from .records import read_events, active_feedbacks, active_studies
    now = now or local_now()
    events = read_events(root)
    refs = {}
    for event in active_studies(events):
        if event["local_date"] == now.date().isoformat() and event.get("action") == "learned":
            refs[event["card_id"]] = event["card_version"]
    attempts = {e["id"]: e for e in events if e["kind"] == "attempt"}
    for feedback in active_feedbacks(events):
        attempt = attempts[feedback["target_id"]]
        if attempt["local_date"] == now.date().isoformat() and feedback["assessment"] != "unverified":
            for ref in attempt["question_snapshot"].get("card_refs", []):
                refs.setdefault(ref["id"], ref["version"])
    if include_due:
        for state in recitation.progress(root, now):
            if state["due"]:
                refs.setdefault(state["id"], state["version"])
    cards = [recitation.load(root, key, version) for key, version in sorted(refs.items())]
    if not cards:
        raise ExamError("no_studied_cards", "今天还没有实际背诵/复背记录；先card --complete记录自报完成，或提交真实抽查反馈。计划中的未学卡不会进入自测。")
    return cards


def budget(root, now=None):
    from .daily import snapshots, task_state
    now = now or local_now()
    on = now.date().isoformat()
    plans = snapshots(root, on)
    if not plans:
        raise ExamError("daily_plan_required", "先说明当天时间并用daily建立计划，再分配自测预算")
    task = next((t for t in reversed(plans[-1]["tasks"]) if t["kind"] == "self_test" and not t.get("question_ids") and not t.get("budget_retired") and task_state(root, t, on) != "已跳过"), None)
    if not task:
        raise ExamError("self_test_budget_required", "本次计划没有待执行自测；可daily --remaining调整剩余预算并安排新任务")
    allocated = sum(len(bank["questions"]) * bank["question_minutes"] for bank in sets(root, on) if bank.get("task_id") == task["id"])
    config = study_settings.get(root)
    return task, max(0, (task["minutes"] - allocated) // config["question_minutes"])


def context(root, now=None, include_due=False):
    cards = studied_cards(root, now, include_due)
    task, available = budget(root, now)
    return {"cards": cards, "task_id": task["id"], "remaining_question_slots": available,
            "estimated_minutes_per_question": study_settings.get(root)["question_minutes"],
            "instructions": "供教师拟题使用：每题只考一张已背卡覆盖的point_ids，先固定答案与要点；不向学生展示本上下文/答案。用self-test import保存后通过next出题。",
            "draft_format": {"questions": [{"card_id": "已背卡ID", "card_version": "版本", "point_ids": ["本题考查要点ID"], "kind": "简答", "stem": "题干", "answer": "依据所选要点的完整参考答案"}]}}


def create(root, count=None, draft=None, new=False, now=None, include_due=False):
    now = now or local_now()
    on = now.date().isoformat()
    folder = inside(root, "userdata/daily-self-tests")
    with lock(folder / "write.lock"):
        existing = sets(root, on)
        draft_hash = digest(json.dumps(draft, ensure_ascii=False, sort_keys=True)) if draft is not None else None
        duplicate = next((bank for bank in existing if draft_hash and bank.get("draft_hash") == draft_hash), None)
        if duplicate:
            return {"reused": True, "set_id": duplicate["id"], "next": next_question(root, duplicate["id"], now)}
        # Opening the same session never silently creates another paper or spends budget again.
        if existing and not new and draft is None:
            return {"reused": True, "set_id": existing[-1]["id"], "next": next_question(root, existing[-1]["id"], now)}
        cards = studied_cards(root, now, include_due)
        by_id = {card["id"]: card for card in cards}
        task, slots = budget(root, now)
        if slots < 1:
            raise ExamError("self_test_budget_exhausted", "本次自测预算已分配；继续当前题目，或明确调整剩余时间后再出新题")
        maximum = min(slots, study_settings.get(root)["max_self_test_questions"])
        if draft is None:
            if count is not None and (type(count) is not int or not 1 <= count <= 10):
                raise ExamError("invalid_count", "题数应为1—10")
            selected = cards[:min(count or maximum, maximum)]
            draft = {"questions": [{"card_id": card["id"], "card_version": card["version"], "point_ids": [p["id"] for p in card["points"]], "kind": "简答", "stem": card["prompt"], "answer": card["body"]} for card in selected]}
        questions = draft.get("questions") if isinstance(draft, dict) else None
        if not isinstance(questions, list) or not 1 <= len(questions) <= maximum:
            raise ExamError("invalid_self_test", f"本次预算最多新增{maximum}题，请减少题目或调整时间")
        frozen = []
        from .feedback import text
        from .questions import KINDS
        for i, item in enumerate(questions, 1):
            if not isinstance(item, dict):
                raise ExamError("invalid_self_test", "每题须为对象")
            card = by_id.get(item.get("card_id"))
            if not card or item.get("card_version") != card["version"]:
                raise ExamError("outside_studied_scope", "题目必须绑定今天实际背过的卡片及对应版本")
            point_ids = item.get("point_ids")
            points = {p["id"]: p for p in card["points"]}
            if not isinstance(point_ids, list) or not point_ids or len(point_ids) != len(set(point_ids)) or set(point_ids) - set(points):
                raise ExamError("outside_studied_scope", "考查要点不存在或超出这张卡片")
            if item.get("kind") not in KINDS:
                raise ExamError("invalid_self_test", "使用标准题型；判断说理可标为其他")
            selected = [points[key] for key in point_ids]
            # All selected points are required for this question; untargeted points stay unmeasured.
            rubric = [{**p, "importance": "core"} for p in selected]
            frozen.append({"id": "q-" + str(i), "stem": text(item.get("stem"), "自测题干"), "context": "", "subject": card["subject"], "kind": item["kind"], "completeness": "complete", "practice_kind": "daily_self_test",
                           "card_refs": [{"id": card["id"], "version": card["version"], "point_ids": point_ids}], "knowledge_points": ["card:" + card["id"]],
                           "rubric": {"version": card["version"] + "-" + digest(json.dumps(point_ids))[:8], "items": rubric}, "evidence": [e for p in selected for e in p["evidence"]],
                           "answer": {"text": text(item.get("answer"), "完整参考答案"), "status": "lecture_recitation_reference_not_official"}, "task_id": task["id"]})
        bank = {"schema_version": 1, "name": "今日讲义自测（AI依据已背内容整理，非历年真题）", "source_type": "ai_generated", "study_date": on, "task_id": task["id"], "question_minutes": study_settings.get(root)["question_minutes"], "questions": frozen, "draft_hash": draft_hash}
        version = digest(json.dumps(bank, ensure_ascii=False, sort_keys=True))[:16]
        bank.update(id="daily-" + on.replace("-", "") + "-" + version, version=version)
        if any(s["id"] == bank["id"] for s in existing):
            return {"reused": True, "set_id": bank["id"], "next": next_question(root, bank["id"], now)}
        prose = "# " + on + " 今日背诵自测\n\nAI依据今日已背内容整理；题干视图不含答案。\n\n" + "\n\n".join(f"## 第{i}题\n{q['stem']}" for i, q in enumerate(frozen, 1))
        md.append(folder / (on + ".md"), "self-test", bank, prose)
    return {"set_id": bank["id"], "generated_count": len(frozen), "reused": False, "next": next_question(root, bank["id"], now),
            "message": "默认生成已背卡的闭卷回忆题。需要判断/比较/案例等变式时，Agent依据self-test context拟题，再self-test import；不机械凑题数。"}


def next_question(root, set_id=None, now=None):
    from .records import read_events, active_feedbacks
    from .questions import public_question
    now = now or local_now()
    available = sets(root, now.date().isoformat())
    bank = next((s for s in available if s["id"] == set_id), None) if set_id else available[-1] if available else None
    if not bank:
        raise ExamError("unknown_self_test", "今天还没有该自测任务")
    events = read_events(root)
    attempts = {e["id"]: e for e in events if e["kind"] == "attempt"}
    feedbacks = active_feedbacks(events)
    graded = {attempts[e["target_id"]]["question_id"] for e in feedbacks if e["assessment"] != "unverified"}
    from .daily import snapshots, task_state
    plans = snapshots(root, now.date().isoformat())
    allowed = None
    if plans:
        active = [t for t in plans[-1]["tasks"] if t["kind"] == "self_test" and not t.get("budget_retired") and task_state(root, t, now.date().isoformat(), events) != "已跳过"]
        fresh_ids = {t["id"] for t in active if not t.get("question_ids")}
        allowed = {qid for t in active for qid in t.get("question_ids", [])}
        allowed.update(s["id"] + ":" + q["id"] for s in available if s["task_id"] in fresh_ids for q in s["questions"])
        if set_id is None:
            bank = next((s for s in available if any(s["id"] + ":" + q["id"] in allowed - graded for q in s["questions"])), bank)
    done = sum(bank["id"] + ":" + q["id"] in graded for q in bank["questions"])
    for item in bank["questions"]:
        qid = bank["id"] + ":" + item["id"]
        if qid not in graded:
            if allowed is not None and qid not in allowed:
                continue
            pending = next((a for a in reversed(list(attempts.values())) if a["question_id"] == qid), None)
            unresolved = next((e for e in feedbacks if e["question_id"] == qid and e["assessment"] == "unverified"), None)
            return {"completed": False, "graded": done, "total": len(bank["questions"]), "question": public_question(bank, item), "awaiting_feedback_attempt": pending["id"] if pending else None, "pending_verification": bool(unresolved)}
    if done < len(bank["questions"]):
        return {"completed": False, "budget_complete": True, "graded": done, "total": len(bank["questions"]), "message": "本次预算内的题已结束，仍有题目顺延；调整剩余时间后再继续，不算整组通过"}
    return {"completed": True, "graded": done, "total": len(bank["questions"]), "message": "本组已反馈；覆盖程度查看recitation-review，不能把未测要点算成已通过"}
