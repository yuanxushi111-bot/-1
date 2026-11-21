"""Budgeted daily assignments in append-only Markdown; completion comes from journals."""
from .common import ExamError, digest, inside, local_now, lock
from . import markdown_store as md, recitation, study_settings


def path(root, on):
    return inside(root, "userdata/daily-plans/" + on + ".md")


def snapshots(root, on):
    return md.read(path(root, on), "plan")


def task_state(root, task, on, events=None):
    from .records import read_events, active_feedbacks, active_studies
    from .selftests import sets
    events = events if events is not None else read_events(root)
    studies = [e for e in active_studies(events) if e["local_date"] == on]
    order = {e["id"]: i for i, e in enumerate(events)}
    actions = [e for e in studies if e.get("task_id") == task["id"]]
    skip_order = order[actions[-1]["id"]] if actions and actions[-1]["action"] == "skipped" else -1

    def status(done, fallback="待开始"):
        latest_done = max((order[e["id"]] for e in done), default=-1)
        return "已完成" if latest_done >= 0 and latest_done > skip_order else "已跳过" if skip_order >= 0 else fallback

    if task["kind"] == "summary":
        return status([e for e in actions if e["action"] == "task_done"])
    if task["kind"] == "learn":
        matching = [e for e in studies if e.get("card_id") == task["card_id"] and e.get("card_version") == task["card_version"]]
        return status([e for e in matching if e["action"] == "learned"], "进行中" if matching else "待开始")
    attempts = {e["id"]: e for e in events if e["kind"] == "attempt"}
    feedbacks = active_feedbacks(events)
    if task["kind"] == "review":
        matching = [e for e in feedbacks if attempts[e["target_id"]]["local_date"] == on and any(r["id"] == task["card_id"] and r["version"] == task["card_version"] for r in attempts[e["target_id"]]["question_snapshot"].get("card_refs", []))]
        return status([e for e in matching if e["assessment"] != "unverified"], "待核实" if matching else "待开始")
    matching = [s for s in sets(root, on) if s.get("task_id") == task["id"]]
    if task.get("question_ids"):
        matching = sets(root, on)
    if not matching:
        return status([])
    qids = set(task["question_ids"]) if task.get("question_ids") else {s["id"] + ":" + q["id"] for s in matching for q in s["questions"]}
    graded = {attempts[e["target_id"]]["question_id"] for e in feedbacks if e["assessment"] != "unverified" and attempts[e["target_id"]]["local_date"] == on}
    return status([e for e in feedbacks if attempts[e["target_id"]]["question_id"] in qids and e["assessment"] != "unverified"] if qids <= graded else [], "进行中")


def project(root, plan):
    from .records import read_events
    events = read_events(root)
    tasks = [{**t, "status": task_state(root, t, plan["date"], events)} for t in plan["tasks"]]
    pending = [t for t in tasks if t["status"] not in {"已完成", "已跳过"}]
    return {**plan, "tasks": tasks, "pending_estimated_minutes": sum(t["minutes"] for t in pending), "completed_tasks": sum(t["status"] == "已完成" for t in tasks), "time_is_estimated": True}


def render(plan):
    lines = [f"# {plan['date']} 每日学习计划 · 修订{plan['revision']}", "", f"本次待办预算：{plan['minutes']}分钟；模式：{plan['budget_mode']}。用时为估计，不是实际计时。", "", "| 任务 | 内容 | 预计分钟 | 状态快照 |", "| --- | --- | ---: | --- |"]
    for task in plan["tasks"]:
        lines.append(f"| {task['kind']} | {task['title'].replace('|', '／')} | {task['minutes']} | {task.get('status', '待开始')} |")
    lines += ["", "当前状态从日期学习日志重建；此计划及修订保留原文。"]
    if plan["deferred"]:
        lines += ["", "## 顺延", *["- " + item for item in plan["deferred"]]]
    if plan["warnings"]:
        lines += ["", "## 提示", *["- " + item for item in plan["warnings"]]]
    return "\n".join(lines)


def today(root, minutes=None, remaining=None, subject=None, revise=False, now=None):
    now = now or local_now()
    on = now.date().isoformat()
    if minutes is not None and remaining is not None:
        raise ExamError("invalid_budget", "minutes与remaining不能同时指定")
    settings = study_settings.get(root)
    with lock(inside(root, "userdata/daily-plans/write.lock")):
        history = snapshots(root, on)
        old = history[-1] if history else None
        if old and minutes is None and remaining is None and subject is None and not revise:
            result = project(root, old)
            # Append a new progress snapshot only when journal-derived status actually changed.
            if [t["status"] for t in result["tasks"]] != [t.get("status") for t in old["tasks"]]:
                result["revision"] += 1
                md.append(path(root, on), "plan", result, render(result))
            return {**result, "path": path(root, on).relative_to(root).as_posix(), "rendered_plan": render(result)}
        requested = remaining if remaining is not None else minutes
        if requested is None:
            requested = old["minutes"] if old else settings["daily_minutes"]
        if requested is None:
            raise ExamError("time_required", "请告诉我今天可学习多久，例如 daily --minutes 30；不会默认沿用昨天时间")
        if type(requested) is not int or not 5 <= requested <= 480:
            raise ExamError("invalid_budget", "当前待办预算应为5—480分钟")
        subject = subject if subject is not None else old.get("subject") if old else None
        if old and requested == old["minutes"] and subject == old.get("subject") and remaining is None and not revise:
            result = project(root, old)
            return {**result, "path": path(root, on).relative_to(root).as_posix(), "rendered_plan": render(result)}
        revision = old["revision"] + 1 if old else 1
        from .records import read_events, active_studies, active_feedbacks
        from .mistakes import list_mistakes
        events = read_events(root)
        states = recitation.progress(root, now)
        state_by_id = {s["id"]: s for s in states}
        weak = {m["question_id"] for m in list_mistakes(root) if m["status"] in {"待复习", "复测中"}}
        eligible = [s for s in states if s["source_id"] == settings["main_source_id"] and s["status"] != "待核实" and (not subject or subject in s["subject"])]
        completed = {}
        for previous in history:
            for task in previous["tasks"]:
                if task_state(root, task, on, events) == "已完成":
                    completed[task["id"]] = {**task, "status": "已完成", "budget_retired": True}
        tasks, deferred, warnings = list(completed.values()), [], []
        # Completed work is retained outside the new pending-work budget.
        spent, overhead = 0, 1 if requested < 20 else 2
        review_minutes, question_minutes = settings["review_minutes"], settings["question_minutes"]

        def add(kind, title, cost, card=None, reason=""):
            nonlocal spent
            identity = on + kind + (card["id"] + card["version"] if card else str(revision))
            task = {"id": "t-" + digest(identity)[:14], "kind": kind, "title": title, "minutes": cost, "reason": reason, "status": "待开始"}
            if card:
                task.update(card_id=card["id"], card_version=card["version"], question_id=recitation.question_bank(recitation.load(root, card["id"]))["id"] + ":recall")
            if task["id"] not in completed:
                tasks.append(task)
                spent += cost
            return task

        reviews = [s for s in eligible if s["due"] or weak.intersection(s["related_question_ids"])]
        reviews.sort(key=lambda s: (s.get("next_review") or on, -s["error_count"], s["id"]))
        review_cap = max(review_minutes, requested // 2) if reviews else 0
        for card in reviews:
            if spent + review_minutes <= min(requested - overhead, review_cap):
                add("review", card["title"], review_minutes, card, "到期复背或关联真题存在未解决错点；先闭卷作答")
            else:
                deferred.append("到期复背顺延：" + card["title"])
        from .selftests import sets
        attempts = {e["id"]: e for e in events if e["kind"] == "attempt"}
        graded = {attempts[e["target_id"]]["question_id"] for e in active_feedbacks(events) if e["assessment"] != "unverified"}
        skipped_ids = {e["task_id"] for e in active_studies(events) if e.get("action") == "skipped"}
        pending_questions = [bank["id"] + ":" + q["id"] for bank in sets(root, on) if bank["task_id"] not in skipped_ids for q in bank["questions"] if bank["id"] + ":" + q["id"] not in graded]
        carry_limit = max(0, (requested - spent - overhead) // question_minutes)
        selected_pending = pending_questions[:carry_limit]
        if selected_pending:
            task = add("self_test", "继续已出但尚未完成的自测", len(selected_pending) * question_minutes, reason="沿用已有题目，不在缩短时间后另加一组")
            task["question_ids"] = selected_pending
        if len(selected_pending) < len(pending_questions):
            deferred.append(f"尚有{len(pending_questions)-len(selected_pending)}道已出自测题超出本次预算，等待重新安排")
        learned_today = {e["card_id"] for e in active_studies(events) if e.get("action") == "learned" and e["local_date"] == on}
        new_cards = [s for s in eligible if s["status"] == "未学习" and s["id"] not in learned_today and all(state_by_id.get(k, {}).get("status") not in {None, "未学习", "待核实"} for k in s["prerequisites"])]
        new_cards.sort(key=lambda s: ({"A1": 0, "A2": 1, "B": 2}[s["priority"]], s["id"]))
        max_new = 1 if requested < 45 else 2
        added_new = 0
        for card in new_cards:
            if added_new < max_new and spent + card["learn_minutes"] + question_minutes + overhead <= requested:
                add("learn", card["title"], card["learn_minutes"], card, "依据主讲义的新主题，预算包含理解、背诵和立即复述")
                added_new += 1
        if not added_new and not reviews and not learned_today:
            short = next((card for card in new_cards if spent + card["learn_minutes"] + overhead <= requested), None)
            if short:
                add("learn", short["title"], short["learn_minutes"], short, "短时首次学习一个完整小主题；预算不足的自测留待后续，不压缩成虚假的完成")
        if not pending_questions and spent + question_minutes + overhead <= requested and (learned_today or any(t["kind"] in {"review", "learn"} for t in tasks)):
            desired = 1 if requested < 20 else 2 if requested < 45 else settings["max_self_test_questions"]
            count = min(desired, settings["max_self_test_questions"], (requested - spent - overhead) // question_minutes)
            add("self_test", "根据今日实际背诵内容自测", count * question_minutes, reason="每题预算含作答与反馈；只从今天实际学习的卡片出题")
        add("summary", "记录完成情况与下次复背", overhead, reason="保存真实经历，不以自报背完代替抽查通过")
        if not states:
            warnings.append("当前尚无背诵卡；先按主讲义候选原文建立小批卡片，再daily --revise。")
        elif not any(t["kind"] in {"learn", "review", "self_test"} and t.get("status") != "已完成" for t in tasks):
            warnings.append("当前时间/科目/前置条件下没有可安排的新任务；可复背已学卡，或按原讲义建立下一批卡片。")
        plan = {"schema_version": 1, "date": on, "revision": revision, "minutes": requested, "budget_mode": "remaining" if remaining is not None else "pending_estimate", "subject": subject, "tasks": tasks, "deferred": deferred, "warnings": warnings}
        result = project(root, plan)
        if result["pending_estimated_minutes"] > requested:
            raise ExamError("budget_overrun", "待办预算计算超限，未保存计划")
        md.append(path(root, on), "plan", result, render(result))
        return {**result, "path": path(root, on).relative_to(root).as_posix(), "rendered_plan": render(result)}


def validate_study(root, payload, now):
    action = payload.get("action")
    if action not in {"viewed", "learned", "skipped", "task_done"}:
        raise ExamError("invalid_study", "action应为viewed、learned、skipped或task_done")
    result = {"action": action, "text": payload.get("text", "自报学习完成，未判定独立通过" if action == "learned" else "学习任务记录")}
    if not isinstance(result["text"], str):
        raise ExamError("invalid_study", "text应为文本")
    if action in {"viewed", "learned"}:
        card = recitation.load(root, payload.get("card_id"), payload.get("card_version"))
        result.update(card_id=card["id"], card_version=card["version"], card_title=card["title"], source_hash=card["source_hash"])
    else:
        history = snapshots(root, now.date().isoformat())
        task = next((t for p in reversed(history) for t in p["tasks"] if t["id"] == payload.get("task_id")), None)
        if not task:
            raise ExamError("unknown_task", "找不到今天的任务")
        if action == "task_done" and task["kind"] != "summary":
            raise ExamError("actual_attempt_required", "学习卡用learned，自测/复测须有真实作答反馈，不能手动勾选为通过")
        result.update(task_id=task["id"], task_title=task["title"])
    return result
