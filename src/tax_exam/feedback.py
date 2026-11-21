"""Validate source-based answers and per-point evaluations; never grade by keyword count."""
import json

from .common import ExamError, digest
from .library import EVIDENCE_ROLES, read_block
from .questions import get_question

POINT_STATES = {"covered": "已覆盖", "partial": "部分覆盖", "missing": "遗漏", "incorrect": "错误", "uncertain": "待核实"}


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ExamError("invalid_feedback", name + "必须为非空文本")
    return value


def verify_evidence(root, items):
    if not isinstance(items, list):
        raise ExamError("invalid_evidence", "evidence应为列表")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ExamError("invalid_evidence", "引文必须为对象")
        block = read_block(root, item.get("block_id"), text(item.get("quote"), "quote"))
        if block["role"] not in EVIDENCE_ROLES:
            raise ExamError("not_primary_evidence", "重点清单和批注不能代替教材、讲义或明确标注的复习资料证据")
        result.append({"block_id": block["id"], "source_id": block["source_id"], "source_hash": block["source_hash"], "source_title": block["title"], "path": block["path"], "pdf_page_start": block["pdf_page_start"], "pdf_page_end": block["pdf_page_end"], "source_part": block.get("source_part"), "merged_page_start": block.get("merged_page_start"), "merged_page_end": block.get("merged_page_end"), "historical": bool(block.get("historical")), "quote": item["quote"]})
    return result


def answer_context(root, attempt):
    question = get_question(root, attempt["question_id"], True)
    if question["bank_version"] != attempt["question_snapshot"]["bank_version"]:
        raise ExamError("question_changed", "题库版本已变化，请先核对原作答对应的题目版本")
    reference = question.get("answer")
    available = bool(reference and isinstance(reference.get("text"), str) and reference["text"].strip())
    return {"attempt_id": attempt["id"], "question": question, "answer_available": available,
            "next_action": "展示题库参考答案，再逐点分析" if available else "检索教材并生成带出处的参考答案，再逐点分析",
            "display_order": ["简短判定", "完整参考答案", "要点对照分析", "复习安排"]}


def validate_reference(root, payload, attempt):
    context = answer_context(root, attempt)
    raw = payload.get("reference_answer")
    if raw is None and context["answer_available"]:
        raw = {"origin": "bank"}
    if not isinstance(raw, dict):
        raise ExamError("reference_required", "无题库答案时必须提供依据教材生成的reference_answer，或明确标记unavailable")
    origin = raw.get("origin")
    existing = context["question"].get("answer")
    result = {"origin": origin, "question_id": attempt["question_id"], "bank_version": context["question"]["bank_version"]}
    if origin in {"bank", "bank_with_supplement"}:
        if not context["answer_available"]:
            raise ExamError("no_bank_answer", "题库没有可用参考答案，不能伪称题库答案")
        result.update(text=existing["text"], status=existing["status"], source_snapshot=existing)
        if existing["status"] == "lecture_recitation_reference_not_official":
            result["evidence"] = verify_evidence(root, context["question"].get("evidence", []))
        if raw.get("text") is not None and raw["text"] != existing["text"]:
            raise ExamError("bank_answer_changed", "原答案必须保持原文；修订请用bank_with_supplement另列补充")
        if origin == "bank_with_supplement":
            result["supplement"] = text(raw.get("supplement"), "supplement")
            result["evidence"] = verify_evidence(root, raw.get("evidence", []))
            if not result["evidence"]:
                raise ExamError("no_evidence", "教材补充必须有原文证据")
    elif origin == "textbook_generated":
        if context["answer_available"]:
            raise ExamError("bank_answer_available", "已有题库答案；请先展示原答案，必要时使用bank_with_supplement")
        result.update(text=text(raw.get("text"), "参考答案"), status="ai_textbook_reference_not_official", evidence=verify_evidence(root, raw.get("evidence", [])))
        if not result["evidence"]:
            raise ExamError("no_evidence", "生成参考答案必须附教材引文")
    elif origin == "unavailable":
        if context["answer_available"]:
            raise ExamError("bank_answer_available", "题库已有参考答案，不能省略；保留原文并将争议要点标记待核实")
        result.update(text=raw.get("text", "现有资料不足以形成完整参考答案。"), status="insufficient_evidence", reason=text(raw.get("reason"), "资料不足原因"))
    else:
        raise ExamError("invalid_reference_origin", "origin应为bank、bank_with_supplement、textbook_generated或unavailable")
    return result


def validate_feedback(root, payload, attempt):
    reference = validate_reference(root, payload, attempt)
    question = answer_context(root, attempt)["question"]
    frozen = question.get("rubric") if question.get("practice_kind") in {"recitation", "daily_self_test"} else None
    if frozen:
        from .recitation import load
        for ref in question["card_refs"]:
            load(root, ref["id"], ref["version"])
    rubric = payload.get("rubric", frozen)
    if frozen:
        def signature(value):
            return {p["id"]: (p["description"], p["importance"], sorted((v["block_id"], v["quote"]) for v in p["evidence"])) for p in value["items"]}
        if not isinstance(rubric, dict) or rubric.get("version") != frozen["version"] or signature(rubric) != signature(frozen):
            raise ExamError("frozen_rubric_changed", "自测/背诵的考查要点在出题时已经固定，不能看作答后改标准")
    results = payload.get("point_results")
    if not isinstance(rubric, dict) or not isinstance(rubric.get("items"), list) or not 1 <= len(rubric["items"]) <= 40:
        raise ExamError("rubric_required", "反馈必须有1—40项rubric.items，先建立要点再核对作答")
    version = text(rubric.get("version"), "rubric.version")
    if not isinstance(results, list):
        raise ExamError("point_results_required", "反馈必须有point_results")
    by_id = {}
    for result in results:
        if not isinstance(result, dict) or result.get("point_id") in by_id:
            raise ExamError("invalid_point_results", "逐点结果格式无效或ID重复")
        by_id[result.get("point_id")] = result
    verified_items, verified_results, evidence = [], [], []
    ids = set()
    for item in rubric["items"]:
        if not isinstance(item, dict):
            raise ExamError("invalid_rubric", "要点必须为对象")
        key = text(item.get("id"), "要点ID")
        if key in ids:
            raise ExamError("invalid_rubric", "要点ID重复")
        ids.add(key)
        if item.get("importance") not in {"core", "supplement"}:
            raise ExamError("invalid_rubric", "importance应为core或supplement")
        result = by_id.get(key)
        if result is None or result.get("status") not in POINT_STATES:
            raise ExamError("invalid_point_results", "每个要点必须且只能有一项合法状态")
        status = result["status"]
        quote = result.get("student_quote")
        if status == "missing":
            if quote:
                raise ExamError("invented_student_quote", "遗漏项不能虚构对应作答原话")
        elif status != "uncertain":
            if not isinstance(quote, str) or not quote.strip() or quote not in attempt["answer"]:
                raise ExamError("student_quote_mismatch", "逐点判断必须引用使用者原始作答中的真实片段")
        elif quote is not None and (not isinstance(quote, str) or quote not in attempt["answer"]):
            raise ExamError("student_quote_mismatch", "待核实项的作答引文也必须真实")
        refs = verify_evidence(root, item.get("evidence", []))
        if status != "uncertain" and not refs:
            raise ExamError("no_point_evidence", "确定的要点判定必须有教材原文；缺证据时用uncertain")
        evidence.extend(refs)
        verified_items.append({"id": key, "description": text(item.get("description"), "要点内容"), "importance": item["importance"], "evidence": refs})
        verified_results.append({"point_id": key, "status": status, "student_quote": quote, "reason": text(result.get("reason"), "逐点理由"), "error_group": result.get("error_group", key)})
    if ids != set(by_id) or not any(item["importance"] == "core" for item in verified_items):
        raise ExamError("invalid_rubric", "逐点结果与要点不一致，或没有核心要点")
    core = {item["id"] for item in verified_items if item["importance"] == "core"}
    core_results = [item for item in verified_results if item["point_id"] in core]
    unresolved = any(item["status"] == "uncertain" for item in core_results) or reference["origin"] == "unavailable"
    bad = [item for item in core_results if item["status"] in {"partial", "missing", "incorrect"}]
    if unresolved:
        assessment, verdict = "unverified", "暂不能可靠判定"
    elif bad:
        assessment = "needs_work"
        verdict = "存在关键错误" if any(item["status"] == "incorrect" for item in bad) else "部分正确，核心要点尚不完整"
    elif attempt.get("hints_used") or attempt.get("answer_seen"):
        assessment, verdict = "hinted", "提示或看过答案后可答，需独立复测"
    else:
        assessment, verdict = "independent", "本次核心要点已覆盖"
    if payload.get("assessment") is not None and payload["assessment"] != assessment:
        raise ExamError("assessment_mismatch", f"整体判断与要点/提示状态不一致，应为 {assessment}")
    reasons = [{"point_id": item["point_id"], "status": item["status"], "reason": item["reason"]} for item in bad] if not unresolved else []
    if assessment == "hinted":
        reasons.append({"point_id": None, "status": "hinted", "reason": "依赖提示或本轮已看过答案"})
    return {"feedback_format": 2, "reference_answer": reference, "rubric": {"version": version, "content_hash": digest(json.dumps(verified_items, ensure_ascii=False, sort_keys=True)), "items": verified_items}, "point_results": verified_results, "assessment": assessment, "verdict": verdict, "mistake_reasons": reasons, "evidence": list({(v["block_id"], v["quote"]): v for v in evidence + reference.get("evidence", [])}.values())}


def format_feedback(event):
    """One renderer used both in the journal and for the model's response template."""
    def safe(value):
        return str(value).replace("<!--", "&lt;!--")
    ref = event["reference_answer"]
    labels = {"bank": "题库已有参考答案", "bank_with_supplement": "题库参考答案与教材补充", "textbook_generated": "AI依据教材整理，非官方", "unavailable": "资料不足，参考答案暂不完整"}
    lines = ["### 判定", safe(event["verdict"]), "", "### 参考答案", labels[ref["origin"]], "", safe(ref["text"])]
    if ref.get("status") == "lecture_recitation_reference_not_official":
        lines[4] = "讲义背诵/自测参考表达，AI依据讲义整理，非官方答案"
    if ref.get("status") == "source_reference_not_official":
        lines.append("\n来源为截图/题集参考答案，非校方官方标准答案。")
    if ref.get("supplement"):
        lines += ["", "#### 教材补充（与原答案区分）", safe(ref["supplement"])]
    if ref.get("reason"):
        lines += ["", safe(ref["reason"])]
    for source in ref.get("evidence", []):
        location = f"分册{source['source_part']}，" if source.get("source_part") else ""
        location += f"PDF页序{source.get('pdf_page_start') or '缺失'}—{source.get('pdf_page_end') or '缺失'}"
        lines += ["", f"依据：{safe(source['source_title'])}，{location}；`{safe(source['path'])}`；块`{source['block_id']}`", "> " + safe(source["quote"]).replace("\n", "\n> ")]
    lines += ["", "### 要点对照分析"]
    descriptions = {item["id"]: item["description"] for item in event["rubric"]["items"]}
    for item in event["point_results"]:
        lines += [f"- **{safe(descriptions[item['point_id']])}：{POINT_STATES[item['status']]}**", "  - 你的作答：" + safe(item.get("student_quote") or "未找到对应内容"), "  - 分析：" + safe(item["reason"])]
    lines += ["", safe(event.get("feedback", "")), "", "### 复习安排", "待核实，暂不计为确认错题。" if event["assessment"] == "unverified" else "下次复测：" + str(event.get("next_review", "待安排"))]
    return "\n".join(lines) + "\n"
