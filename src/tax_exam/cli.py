"""JSON CLI contract shared by all agent hosts. No model credentials required."""
import argparse
from pathlib import Path
import json
import sqlite3
import sys

from . import __version__
from .common import ExamError, load_json
from . import library, questions, records, mistakes, materials, mineru_adapter
from . import recitation, daily, selftests, study_settings


def parser():
    result = argparse.ArgumentParser(description="税法备考 Skill 本地工具；输出 UTF-8 JSON")
    result.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("index")
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--book")
    search.add_argument("--role", choices=["textbook", "lecture", "bilingual_notes", "guide"])
    read = sub.add_parser("read")
    read.add_argument("block_id")
    read.add_argument("--quote")
    sub.add_parser("banks")
    qs = sub.add_parser("questions")
    qs.add_argument("--bank")
    qs.add_argument("--subject")
    qs.add_argument("--kind")
    qs.add_argument("--source-type", choices=sorted(questions.SOURCE_TYPES))
    qs.add_argument("--include-partial", action="store_true")
    qs.add_argument("--query", default="")
    qs.add_argument("--limit", type=int, default=20)
    question = sub.add_parser("question")
    question.add_argument("question_id")
    question.add_argument("--reveal-answer", action="store_true")
    bank = sub.add_parser("import-bank")
    bank.add_argument("file", type=Path)
    bank.add_argument("--apply", action="store_true")
    markdown = sub.add_parser("import-markdown")
    markdown.add_argument("file", type=Path)
    markdown.add_argument("--bank-id", required=True)
    markdown.add_argument("--name", required=True)
    markdown.add_argument("--subject", required=True)
    markdown.add_argument("--source-type", choices=sorted(questions.SOURCE_TYPES - {"ai_generated"}), default="custom")
    markdown.add_argument("--apply", action="store_true")
    record = sub.add_parser("record")
    record.add_argument("file", type=Path)
    journal = sub.add_parser("records")
    journal.add_argument("--date")
    review = sub.add_parser("review")
    review.add_argument("--on")
    review.add_argument("--all", action="store_true")
    sub.add_parser("materials")
    context = sub.add_parser("answer-context")
    context.add_argument("attempt_id")
    mistake = sub.add_parser("mistakes")
    mistake.add_argument("--status", choices=["待复习", "复测中", "已巩固", "待核实"])
    mistake.add_argument("--subject")
    mistake.add_argument("--due", action="store_true")
    mistake.add_argument("--details", action="store_true")
    mistake.add_argument("--rebuild", action="store_true")
    mistake.add_argument("--on")
    material = sub.add_parser("import-material")
    material.add_argument("file", type=Path)
    material.add_argument("--role", choices=sorted(materials.ROLES - {"exam", "answers"}), default="textbook")
    material.add_argument("--title")
    material.add_argument("--id")
    material.add_argument("--apply", action="store_true")
    sub.add_parser("mineru-check")
    convert = sub.add_parser("convert")
    convert.add_argument("file", type=Path, nargs="?")
    convert.add_argument("--tier", choices=["basic", "standard", "advanced", "flash"])
    convert.add_argument("--remote", action="store_true")
    convert.add_argument("--resume")
    sub.add_parser("cards")
    card = sub.add_parser("card")
    card.add_argument("card_id")
    mode = card.add_mutually_exclusive_group()
    mode.add_argument("--learn", action="store_true")
    mode.add_argument("--complete", action="store_true")
    mode.add_argument("--reference", action="store_true", help="教师核对正文，不表示学生已经看过")
    card.add_argument("--request-id")
    save_card = sub.add_parser("card-save")
    save_card.add_argument("file", type=Path)
    save_card.add_argument("--apply", action="store_true")
    candidate = sub.add_parser("card-candidates")
    candidate.add_argument("query")
    candidate.add_argument("--limit", type=int, default=5)
    day_plan = sub.add_parser("daily")
    time = day_plan.add_mutually_exclusive_group()
    time.add_argument("--minutes", type=int)
    time.add_argument("--remaining", type=int)
    day_plan.add_argument("--subject")
    day_plan.add_argument("--revise", action="store_true")
    recall = sub.add_parser("recitation-review")
    recall.add_argument("--due", action="store_true")
    self_test = sub.add_parser("self-test")
    self_test.add_argument("action", choices=["context", "create", "import", "next", "list"])
    self_test.add_argument("--file", type=Path)
    self_test.add_argument("--count", type=int)
    self_test.add_argument("--new", action="store_true")
    self_test.add_argument("--set-id")
    self_test.add_argument("--include-due", action="store_true", help="仅在用户明确要求额外复测旧卡时使用")
    settings = sub.add_parser("settings")
    settings.add_argument("file", type=Path, nargs="?")
    settings.add_argument("--apply", action="store_true")
    return result


def dispatch(args):
    root = args.root.resolve()
    command = args.command
    if command == "doctor":
        info = {"version": __version__, "default_host": "deepseekharness", "python": sys.version.split()[0], "root": str(root), "record_directory": "userdata/study-records", "journal_naming": "YYYY-MM-DD.md"}
        try:
            data = library.manifest(root)
            for source in data["sources"]:
                library.checked_source(root, source)
            for item in data.get("files", []):
                from .common import file_hash, inside
                if file_hash(inside(root, item["path"])) != item["sha256"]:
                    raise ExamError("asset_changed", "资料附件已变更或丢失，请重新导入资料")
            info.update(material_sources=len(data["sources"]), banks=questions.bank_summary(root))
            info["recitation_cards"] = len(recitation.catalog(root)["current"])
            info["study_settings"] = study_settings.get(root)
            conn = library.open_index(root)
            info["blocks"] = conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
            conn.close()
            info["ready"] = True
        except ExamError as error:
            info.update(ready=False, issue={"code": error.code, "message": str(error)})
        return info
    if command == "index":
        return library.build_index(root)
    if command == "search":
        return library.search(root, args.query, args.limit, args.book, args.role)
    if command == "read":
        return library.read_block(root, args.block_id, args.quote)
    if command == "banks":
        return questions.bank_summary(root)
    if command == "questions":
        items = questions.list_questions(root, args.bank, args.subject, args.kind, args.source_type, args.include_partial)
        if args.query:
            items = [item for item in items if args.query.lower() in (item["stem"] + " " + item.get("context", "")).lower()]
        return {"total": len(items), "questions": items[:max(1, min(args.limit, 100))]}
    if command == "question":
        return questions.get_question(root, args.question_id, args.reveal_answer)
    if command == "import-bank":
        return questions.import_bank(root, args.file, args.apply)
    if command == "import-markdown":
        return questions.import_markdown(root, args.file, args.bank_id, args.name, args.subject, args.source_type, args.apply)
    if command == "record":
        return records.save_event(root, load_json(args.file))
    if command == "records":
        return records.read_events(root, args.date)
    if command == "review":
        states = records.review_state(root, args.on)
        return [item for item in states if args.all or item["due"]]
    if command == "materials":
        return library.manifest(root)["sources"]
    if command == "answer-context":
        from .feedback import answer_context
        attempt = next((item for item in records.read_events(root) if item["id"] == args.attempt_id and item["kind"] == "attempt"), None)
        if not attempt:
            raise ExamError("unknown_attempt", "请先保存真实作答，再读取作答后的参考答案")
        return answer_context(root, attempt)
    if command == "mistakes":
        if args.rebuild:
            return mistakes.rebuild(root)
        return mistakes.list_mistakes(root, args.status, args.subject, args.due, args.details, args.on)
    if command == "import-material":
        return materials.import_material(root, args.file, args.role, args.title, args.id, args.apply)
    if command == "mineru-check":
        return mineru_adapter.check(root)
    if command == "convert":
        if not args.file and not args.resume:
            raise ExamError("file_required", "指定文件或 --resume 任务ID")
        return mineru_adapter.convert(root, args.file, args.tier, args.remote, args.resume)
    if command in {"cards", "recitation-review"}:
        states = recitation.progress(root)
        return [s for s in states if command == "cards" or not args.due or s["due"]]
    if command == "card":
        if args.reference:
            card = recitation.load(root, args.card_id)
            return {"card": card, "rendered_card": recitation.render(card), "teacher_reference_only": True}
        return recitation.view(root, args.card_id, args.learn, args.complete, request_id=args.request_id)
    if command == "card-save":
        return recitation.save(root, load_json(args.file), args.apply)
    if command == "card-candidates":
        return recitation.candidates(root, args.query, args.limit)
    if command == "daily":
        return daily.today(root, args.minutes, args.remaining, args.subject, args.revise)
    if command == "self-test":
        if args.action == "context":
            return selftests.context(root, include_due=args.include_due)
        if args.action == "next":
            return selftests.next_question(root, args.set_id)
        if args.action == "list":
            from .common import local_now
            return [{"id": s["id"], "questions": len(s["questions"]), "study_date": s["study_date"]} for s in selftests.sets(root, local_now().date().isoformat())]
        if args.action == "import" and not args.file:
            raise ExamError("file_required", "self-test import须指定 --file JSON")
        return selftests.create(root, args.count, load_json(args.file) if args.action == "import" else None, args.new, include_due=args.include_due)
    if command == "settings":
        return study_settings.update(root, args.file, args.apply) if args.file else study_settings.get(root)
    raise ExamError("unknown_command", "未知命令")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        data = dispatch(args)
        print(json.dumps({"ok": True, "version": __version__, "data": data}, ensure_ascii=False))
        if args.command == "doctor" and not data["ready"]:
            raise SystemExit(1)
    except (ExamError, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(json.dumps({"ok": False, "version": __version__, "error": {"code": getattr(error, "code", "invalid_input"), "message": str(error)}}, ensure_ascii=False))
        raise SystemExit(2)
