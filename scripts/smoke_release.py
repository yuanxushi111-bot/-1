"""Unpack releases into a fresh path and exercise the bundled Windows runtime."""
from datetime import date, timedelta
from pathlib import Path
import json
import os
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tax_exam.common import file_hash, inside, write_json
from tax_exam import __version__


def smoke():
    work = inside(ROOT, ".work/release-check/移动 中文路径 " + uuid.uuid4().hex[:8])
    work.mkdir(parents=True)
    public = ROOT / f"dist/tax-exam-skill-{__version__}-public-source.zip"
    private = ROOT / f"dist/tax-exam-skill-{__version__}-windows-x64-private.zip"
    with zipfile.ZipFile(public) as archive:
        names = [name.split("/", 1)[1] for name in archive.namelist()]
        assert not any(name.startswith(("library/", "indexes/", "runtime/", "runtime-mineru/", "userdata/")) for name in names)
    with zipfile.ZipFile(private) as archive:
        for name in archive.namelist():
            inside(work, name)  # Verify every resolved destination before extraction.
        archive.extractall(work)
    stage = work / f"tax-exam-skill-{__version__}-windows-x64-private"
    manifest = json.loads((stage / "release-manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        assert file_hash(inside(stage, item["path"])) == item["sha256"], item["path"]
    assert not (stage / "userdata").exists()
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PATH"] = str(Path(env.get("SystemRoot", "C:/Windows")) / "System32")

    def run(*arguments):
        result = subprocess.run([str(stage / "runtime/python.exe"), str(stage / "tax_exam.py"), *arguments], cwd=stage, env=env, capture_output=True, encoding="utf-8", timeout=100)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        response = json.loads(result.stdout)
        assert response["ok"]
        return response["data"]

    doctor = run("doctor")
    assert doctor["ready"]
    result = subprocess.run(["cmd.exe", "/d", "/c", "call", str(stage / "tools.cmd"), "doctor"], cwd=stage, env=env, capture_output=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout)["data"]["ready"]
    evidence = run("search", "税收抵免法", "--limit", "1")["results"][0]
    quote = evidence["text"].strip()[:80]
    assert run("read", evidence["id"], "--quote", quote)["quote_verified"]
    question = run("questions", "--bank", "xmu-2023", "--query", "税收抵免法", "--limit", "1")["questions"][0]
    assert "answer" not in question
    request = stage / "request.json"
    write_json(request, {"kind": "attempt", "question_id": question["id"], "answer": "软件验收用自制回答：不会。并非朋友的学习记录。", "hints_used": False})
    attempt = run("record", str(request))
    context = run("answer-context", attempt["event"]["id"])
    assert context["answer_available"]
    write_json(request, {"kind": "feedback", "request_id": "release-grade", "target_id": attempt["event"]["id"], "feedback": "仅验证软件保存与展示顺序，不代表真实教学判断。", "rubric": {"version": "release-smoke-v1", "items": [{"id": "credit-definition", "description": "软件验收用定义要点", "importance": "core", "evidence": [{"block_id": evidence["id"], "quote": quote}]}]}, "point_results": [{"point_id": "credit-definition", "status": "missing", "student_quote": None, "reason": "自制软件验收回答为不会。"}], "knowledge_points": ["税收抵免法"]})
    feedback = run("record", str(request))
    assert feedback["event"]["reference_answer"]["text"] == context["question"]["answer"]["text"]
    rendered = feedback["rendered_feedback"]
    assert rendered.index("### 判定") < rendered.index("### 参考答案") < rendered.index("### 要点对照分析")
    assert run("record", str(request))["duplicate_request"]
    assert run("mistakes")[0]["error_count"] == 1
    assert "history" not in run("mistakes")[0]
    assert (stage / "userdata/mistake-book/错题索引.md").is_file()
    assert run("mistakes", "--rebuild")["items"] == 1
    journal = stage / feedback["path"]
    assert journal.name == feedback["event"]["local_date"] + ".md"
    with journal.open("a", encoding="utf-8") as stream:
        stream.write("\n我的手工验收笔记：保留原文。\n")
    write_json(request, {"kind": "note", "text": "追加验收笔记"})
    run("record", str(request))
    assert "我的手工验收笔记" in journal.read_text(encoding="utf-8")
    due = run("review", "--on", feedback["event"]["next_review"])
    assert due and due[0]["due"]
    preview = run("import-bank", "examples/demo-bank.json")
    assert not preview["applied"]
    assert run("import-bank", "examples/demo-bank.json", "--apply")["applied"]
    assert any(bank["id"] == "demo-library" for bank in run("banks"))
    # V1.2: cold start -> daily plan -> full card -> self-report -> frozen self-test -> journal/mistakes.
    assert doctor["recitation_cards"] >= 1
    day_plan = run("daily", "--minutes", "30", "--subject", "中国税法学")
    assert day_plan["pending_estimated_minutes"] <= 30
    assert run("daily")["tasks"] == day_plan["tasks"]
    learn_task = next(t for t in day_plan["tasks"] if t["kind"] == "learn")
    assert "body" not in run("card", learn_task["card_id"])
    learned = run("card", learn_task["card_id"], "--learn")
    assert learned["card"]["body"] in learned["rendered_card"]
    assert "原讲义依据" in learned["rendered_card"]
    run("card", learn_task["card_id"], "--complete", "--request-id", "release-card-learned")
    assert run("card", learn_task["card_id"], "--complete", "--request-id", "release-card-learned")["record"]["duplicate_request"]
    generated = run("self-test", "create", "--count", "2")
    assert run("self-test", "create")["reused"]
    drill = generated["next"]["question"]
    assert all(key not in drill for key in ("answer", "rubric", "evidence", "body"))
    write_json(request, {"kind": "attempt", "question_id": drill["id"], "answer": "软件验收自制作答：不会，非真实学习记录。", "answer_seen": False})
    recall_attempt = run("record", str(request))["event"]
    assert recall_attempt["answer_seen"]  # Freshly studied material cannot be counted as independent recall.
    recall_context = run("answer-context", recall_attempt["id"])
    write_json(request, {"kind": "feedback", "target_id": recall_attempt["id"], "point_results": [{"point_id": p["id"], "status": "missing", "student_quote": None, "reason": "自制软件验收回答为不会；仅检查流程。"} for p in recall_context["question"]["rubric"]["items"]]})
    recall_feedback = run("record", str(request))
    assert recall_feedback["event"]["assessment"] == "needs_work"
    assert recall_feedback["event"]["reference_answer"]["text"] == learned["card"]["body"]
    assert recall_feedback["mistake_book"]["updated"]
    assert run("self-test", "next")["completed"]
    assert next(c for c in run("recitation-review") if c["id"] == learn_task["card_id"])["independent_pass_days"] == []
    draft = {"questions": [{"card_id": learned["card"]["id"], "card_version": learned["card"]["version"], "point_ids": [learned["card"]["points"][0]["id"]], "kind": "简答", "stem": "软件验收：请复述本卡第一个核心要点的含义。", "answer": learned["card"]["points"][0]["evidence"][0]["quote"]}]}
    write_json(request, draft)
    variant = run("self-test", "import", "--file", str(request))
    assert variant["set_id"] != generated["set_id"]
    assert run("self-test", "import", "--file", str(request))["reused"]
    plan_file = stage / day_plan["path"]
    with plan_file.open("a", encoding="utf-8") as stream:
        stream.write("\n个人验收备注：保留这段文字。\n")
    revised = run("daily", "--remaining", "10")
    assert revised["pending_estimated_minutes"] <= 10
    assert any(t["kind"] == "learn" and t["status"] == "已完成" for t in revised["tasks"])
    assert "个人验收备注" in plan_file.read_text(encoding="utf-8")
    assert (stage / "userdata/daily-self-tests" / (day_plan["date"] + ".md")).is_file()
    material = run("import-material", "examples/materials/demo-textbook.md", "--role", "lecture", "--id", "smoke-material")
    assert not material["applied"]
    assert run("import-material", "examples/materials/demo-textbook.md", "--role", "lecture", "--id", "smoke-material", "--apply")["applied"]
    assert run("search", "借阅额度", "--role", "lecture")["results"]
    assert run("mineru-check")["compatible"]
    assert (stage / ".dsh/skills/mineru-documents/SKILL.md").is_file()
    # A simple local flash conversion exercises spawned services without OCR/model downloads.
    fixture = stage / "fixture.csv"
    fixture.write_text("topic,definition\nRelease check,Self-authored local conversion sample.\n", encoding="utf-8")
    converted = run("convert", str(fixture))
    if converted["status"] == "pending":
        converted = run("convert", "--resume", converted["id"])
    assert converted["status"] == "done", converted
    assert "Self-authored local conversion sample" in Path(converted["output"]).read_text(encoding="utf-8")
    assert run("import-material", converted["output"], "--role", "lecture", "--id", "converted-csv", "--apply")["applied"]
    assert run("search", "Self-authored local conversion sample", "--book", "converted-csv")["results"]
    generator = stage / "make-pdf-fixture.py"
    generator.write_text("from pathlib import Path\nfrom PIL import Image,ImageDraw\nfrom reportlab.pdfgen.canvas import Canvas\nf=Path(__file__).parent\ni=Image.new('RGB',(300,140),'white');d=ImageDraw.Draw(i);d.rectangle((20,20,280,120),outline='blue',width=4);d.text((45,60),'Self-authored fixture',fill='black');i.save(f/'picture.png')\nc=Canvas(str(f/'fixture.pdf'));c.drawString(60,760,'Self-authored PDF page one.');c.showPage();c.drawString(60,760,'Self-authored PDF page two.');c.drawImage(str(f/'picture.png'),60,500,width=300,height=140);c.save()\n", encoding="utf-8")
    subprocess.run([str(stage / "runtime-mineru/python.exe"), str(generator)], cwd=stage, env=env, check=True, timeout=30, capture_output=True)
    pdf = run("convert", str(stage / "fixture.pdf"), "--tier", "flash")
    if pdf["status"] == "pending":
        pdf = run("convert", "--resume", pdf["id"])
    if pdf["status"] == "done":
        assert pdf["images"] >= 1, pdf
        text = Path(pdf["output"]).read_text(encoding="utf-8")
        assert "<!-- page 2 of 2 -->" in text and "Self-authored PDF page two" in text
        assert "(doc:" not in text
        assert run("import-material", pdf["output"], "--role", "lecture", "--id", "converted-pdf", "--apply")["applied"]
        assert run("search", "Self-authored PDF page two", "--book", "converted-pdf")["results"]
    else:
        assert pdf["status"] == "failed" and pdf.get("error_code"), pdf
        assert pdf["remote"] is False
        models = stage / "userdata/mineru/models"
        assert not models.exists() or not any(p.is_file() and ".locks" not in p.parts for p in models.rglob("*")), "Ordinary conversion must not silently download models"
    summary = {"passed": True, "version": __version__, "checks": ["public_private_separation", "all_packaged_file_hashes", "bundled_runtime_without_system_python", "windows_cmd_wrapper", "moved_chinese_space_path", "doctor", "textbook_search_and_quote", "answer_hidden_before_attempt", "answer_context_and_automatic_reference_snapshot", "fixed_answer_before_analysis_order", "rubric_evidence_validation", "daily_markdown_append", "manual_note_preserved", "review_rebuilt_in_new_process", "bank_import_preview_and_apply", "automatic_mistake_book", "mistake_idempotency_and_rebuild", "mistake_drill_hides_answers", "material_import_preview_and_apply", "bundled_mineru_version", "bundled_mineru_local_csv_to_markdown", "converted_csv_import_search", "bundled_mineru_pdf_all_pages_and_local_images", "converted_pdf_import_search", "two_host_skills", "daily_budget_and_stable_reopen", "full_card_with_real_lecture_evidence", "self_report_idempotency", "today_studied_scope_self_test", "frozen_question_answer_and_rubric", "closed_self_test_view", "same_day_exposure_retained", "recitation_feedback_to_mistake_book", "partial_point_variant_import", "self_test_import_idempotency", "remaining_time_keeps_completed_work", "daily_plan_manual_note_preserved", "dated_self_test_markdown"], "material_sources": doctor["material_sources"], "blocks": doctor["blocks"], "question_units": sum(bank["questions"] for bank in doctor["banks"] if bank["source_type"] == "past_exam"), "starter_recitation_cards": doctor["recitation_cards"], "full_lecture_card_coverage": False, "record_name_pattern": "YYYY-MM-DD.md", "ocr_models_included": False}
    summary["pdf_result"] = "all_pages_images_imported" if pdf["status"] == "done" else "missing_models_reported_without_download_or_upload"
    if pdf["status"] != "done":
        summary["checks"].remove("bundled_mineru_pdf_all_pages_and_local_images")
        summary["checks"].remove("converted_pdf_import_search")
        summary["checks"].append("pdf_missing_models_safe_failure_no_silent_download")
    write_json(ROOT / ".work/release-smoke.json", summary)
    write_json(ROOT / ("docs/verification-v" + ".".join(__version__.split(".")[:2]) + ".json"), summary)
    write_json(ROOT / ".work/verified-release-manifest.json", manifest)
    return summary


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(smoke(), ensure_ascii=False))
