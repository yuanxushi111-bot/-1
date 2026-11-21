from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import copy
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tax_exam import feedback, library, materials, mistakes, mineru_adapter, questions, records
from tax_exam.common import ExamError, load_json, write_json


class V11Test(unittest.TestCase):
    def setUp(self):
        base = ROOT / ".work/tests-v11"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temp.name)
        materials.build_library(self.root, demo=True)
        questions.import_bank(self.root, ROOT / "examples/demo-bank.json", True)
        self.now = datetime(2026, 11, 13, 20, 0, tzinfo=timezone(timedelta(hours=8)))
        self.qid = "demo-library:quota"
        self.answer = "归还登记完成后才释放额度。"
        block = next(item for item in library.search(self.root, "归还登记")["results"] if "完成归还登记后释放" in item["text"])
        self.ev = {"block_id": block["id"], "quote": "完成归还登记后释放一个借阅额度"}

    def tearDown(self):
        assert self.root.resolve().is_relative_to((ROOT / ".work/tests-v11").resolve())
        self.temp.cleanup()

    def attempt(self, when=None, **fields):
        return records.save_event(self.root, {"kind": "attempt", "question_id": self.qid, "answer": self.answer, **fields}, when or self.now)["event"]

    def payload(self, attempt, status="covered", **fields):
        return {"kind": "feedback", "target_id": attempt["id"], "feedback": "核对归还条件，再安排迁移验证。", "knowledge_points": ["归还登记"], "rubric": {"version": "demo-v1", "items": [{"id": "registration", "description": "归还登记完成后才释放额度", "importance": "core", "evidence": [self.ev]}]}, "point_results": [{"point_id": "registration", "status": status, "student_quote": None if status in {"missing", "uncertain"} else self.answer, "reason": "按自制演示教材核对该条件。"}], **fields}

    def grade(self, status="covered", when=None, **attempt_fields):
        a = self.attempt(when, **attempt_fields)
        return records.save_event(self.root, self.payload(a, status), when or self.now)

    def test_bank_answer_automatically_snapshotted_and_rendered_before_analysis(self):
        result = self.grade()
        event = result["event"]
        self.assertEqual(event["reference_answer"]["origin"], "bank")
        self.assertEqual(event["reference_answer"]["text"], questions.get_question(self.root, self.qid, True)["answer"]["text"])
        rendered = result["rendered_feedback"]
        self.assertLess(rendered.index("### 判定"), rendered.index("### 参考答案"))
        self.assertLess(rendered.index("### 参考答案"), rendered.index("### 要点对照分析"))
        self.assertIn(event["reference_answer"]["text"], (self.root / result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(mistakes.list_mistakes(self.root), [])

    def test_generated_answer_requires_book_evidence(self):
        bank = load_json(ROOT / "examples/demo-bank.json")
        bank["id"] = "no-answer"
        bank["questions"][0]["answer"] = None
        questions.import_bank(self.root, bank, True)
        self.qid = "no-answer:quota"
        a = self.attempt()
        with self.assertRaisesRegex(ExamError, "reference_answer"):
            records.save_event(self.root, self.payload(a), self.now)
        ref = {"origin": "textbook_generated", "text": "AI依据演示教材整理：需完成归还登记后才释放额度。", "evidence": [self.ev]}
        result = records.save_event(self.root, self.payload(a, reference_answer=ref), self.now)
        self.assertEqual(result["event"]["reference_answer"]["status"], "ai_textbook_reference_not_official")

    def test_bank_answer_cannot_be_silently_rewritten(self):
        a = self.attempt()
        with self.assertRaisesRegex(ExamError, "原答案"):
            records.save_event(self.root, self.payload(a, reference_answer={"origin": "bank", "text": "伪造的原答案"}), self.now)

    def test_five_statuses_are_saved_and_aggregate_consistently(self):
        expected = {"covered": "independent", "partial": "needs_work", "missing": "needs_work", "incorrect": "needs_work", "uncertain": "unverified"}
        for status, assessment in expected.items():
            with self.subTest(status=status):
                result = self.grade(status)
                self.assertEqual(result["event"]["assessment"], assessment)
                self.assertEqual(result["event"]["point_results"][0]["status"], status)

    def test_student_quote_must_match_original_and_missing_cannot_invent_quote(self):
        a = self.attempt()
        data = self.payload(a)
        data["point_results"][0]["student_quote"] = "学生没有说过的话"
        with self.assertRaisesRegex(ExamError, "真实片段"):
            records.save_event(self.root, data, self.now)
        data["point_results"][0]["status"] = "missing"
        with self.assertRaisesRegex(ExamError, "虚构"):
            records.save_event(self.root, data, self.now)

    def test_optional_extension_missing_does_not_create_mistake(self):
        a = self.attempt()
        data = self.payload(a)
        data["rubric"]["items"].append({"id": "extra", "description": "可选背景拓展", "importance": "supplement", "evidence": [self.ev]})
        data["point_results"].append({"point_id": "extra", "status": "missing", "student_quote": None, "reason": "不是本题必要内容"})
        event = records.save_event(self.root, data, self.now)["event"]
        self.assertEqual(event["assessment"], "independent")
        self.assertEqual(mistakes.list_mistakes(self.root), [])

    def test_uncertain_not_counted_as_confirmed_wrong(self):
        self.grade("uncertain")
        item = mistakes.list_mistakes(self.root)[0]
        self.assertEqual(item["status"], "待核实")
        self.assertEqual(item["error_count"], 0)
        self.assertEqual(records.review_state(self.root), [])

    def test_mistake_grouping_cancel_and_retry(self):
        a = self.attempt()
        data = self.payload(a, "missing", request_id="first-grade")
        first = records.save_event(self.root, data, self.now)
        records.save_event(self.root, data, self.now)
        self.assertEqual(mistakes.list_mistakes(self.root)[0]["error_count"], 1)
        self.grade("partial")
        self.assertEqual(len(mistakes.list_mistakes(self.root)), 1)
        self.assertEqual(mistakes.list_mistakes(self.root)[0]["error_count"], 2)
        records.save_event(self.root, {"kind": "cancel", "target_id": first["event"]["id"]}, self.now)
        self.assertEqual(mistakes.list_mistakes(self.root)[0]["error_count"], 1)

    def test_two_cross_day_passes_consolidate_and_same_day_does_not(self):
        self.grade("missing")
        self.grade("covered")
        self.assertEqual(mistakes.list_mistakes(self.root)[0]["status"], "待复习")
        self.grade("covered", self.now + timedelta(days=1))
        self.assertEqual(mistakes.list_mistakes(self.root)[0]["status"], "复测中")
        self.grade("covered", self.now + timedelta(days=2))
        self.assertEqual(mistakes.list_mistakes(self.root)[0]["status"], "已巩固")
        self.grade("incorrect", self.now + timedelta(days=3))
        self.assertEqual(mistakes.list_mistakes(self.root)[0]["status"], "待复习")

    def test_hint_and_answer_seen_are_not_independent(self):
        result = self.grade("covered", hints_used=True)
        self.assertEqual(result["event"]["assessment"], "hinted")
        result = self.grade("covered", answer_seen=True)
        self.assertEqual(result["event"]["assessment"], "hinted")

    def test_same_day_after_feedback_automatically_marks_answer_seen(self):
        self.grade("missing")
        attempt = self.attempt(answer_seen=False)
        self.assertTrue(attempt["answer_seen"])
        event = records.save_event(self.root, self.payload(attempt), self.now)["event"]
        self.assertEqual(event["assessment"], "hinted")

    def test_existing_bank_answer_cannot_be_hidden_as_unavailable(self):
        a = self.attempt()
        with self.assertRaisesRegex(ExamError, "已有参考答案"):
            records.save_event(self.root, self.payload(a, reference_answer={"origin": "unavailable", "reason": "存在争议"}), self.now)

    def test_all_previous_wrong_points_required_for_consolidation(self):
        self.grade("missing")
        a = self.attempt(self.now + timedelta(days=1))
        data = self.payload(a, "missing")
        data["rubric"]["items"][0]["id"] = "second-condition"
        data["point_results"][0]["point_id"] = "second-condition"
        records.save_event(self.root, data, self.now + timedelta(days=1))
        self.grade("covered", self.now + timedelta(days=2))
        self.grade("covered", self.now + timedelta(days=3))
        self.assertNotEqual(mistakes.list_mistakes(self.root)[0]["status"], "已巩固")

    def test_mistake_default_drill_listing_has_no_reference_or_analysis(self):
        self.grade("incorrect")
        item = mistakes.list_mistakes(self.root)[0]
        self.assertNotIn("history", item)
        self.assertNotIn("reference_answer", item)
        detail = mistakes.list_mistakes(self.root, details=True)[0]
        self.assertIn("reference_answer", detail["history"][0]["feedback"])

    def test_derived_view_can_rebuild_and_refuses_manual_overwrite(self):
        self.grade("missing")
        folder = self.root / "userdata/mistake-book"
        assert folder.resolve().is_relative_to(self.root.resolve())
        shutil.rmtree(folder)
        self.assertEqual(mistakes.rebuild(self.root)["items"], 1)
        file = folder / "2026-11-13.md"
        with file.open("a", encoding="utf-8") as stream:
            stream.write("\n手工修改必须保留\n")
        with self.assertRaisesRegex(ExamError, "手工修改"):
            mistakes.rebuild(self.root)
        self.assertIn("手工修改", file.read_text(encoding="utf-8"))

    def test_material_version_archives_old_citation(self):
        old_block = self.ev["block_id"]
        source_dir = self.root / "incoming"
        source_dir.mkdir()
        file = source_dir / "new.md"
        file.write_text("# 自制新资料\n\n<!-- page 1 of 1 -->\n\n## 演示\n\n新增例子。", encoding="utf-8")
        materials.import_material(self.root, file, "lecture", source_id="new-lecture", apply=True)
        block = library.read_block(self.root, old_block)
        self.assertIn("完成归还登记", block["text"])
        file.write_text("# 自制新资料\n\n<!-- page 1 of 1 -->\n\n新版本例子。", encoding="utf-8")
        # Replace full source collection to ensure original block only exists in archive.
        materials.build_library(self.root, source_dir)
        historic = library.read_block(self.root, old_block)
        self.assertTrue(historic["historical"])
        self.assertTrue((self.root / historic["path"]).is_file())

    def test_forged_index_text_cannot_pass_exact_quote_verification(self):
        block = library.read_block(self.root, self.ev["block_id"])
        block["text"] = "伪造的教材正文"
        connection = sqlite3.connect(self.root / "indexes/materials.sqlite")
        connection.execute("UPDATE blocks SET payload=? WHERE id=?", (json.dumps(block, ensure_ascii=False), block["id"]))
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(ExamError, "原始文件不一致"):
            library.read_block(self.root, block["id"], "伪造的教材正文")

    def test_merged_lecture_parts_never_mix(self):
        text = "<!-- source-part:1; pdf-page:1/1 -->\n<!-- page 1 of 1 -->\n\n第一册。\n\n<!-- source-part:2; pdf-page:1/1 -->\n<!-- page 1 of 1 -->\n\n第二册。\n"
        source = {"id": "lecture", "sha256": "demo", "path": "demo.md", "title": "demo", "role": "lecture"}
        blocks = list(library.chunks(text, source))
        self.assertTrue(all(not ("第一册" in block["text"] and "第二册" in block["text"]) for block in blocks))
        self.assertEqual(next(b for b in blocks if "第二册" in b["text"])["merged_page_start"], 2)

    def test_mineru_missing_does_not_upload_or_convert(self):
        with patch("tax_exam.mineru_adapter.shutil.which", return_value=None):
            self.assertFalse(mineru_adapter.check(self.root)["installed"])
        file = self.root / "example.md"
        file.write_text("资料", encoding="utf-8")
        self.assertEqual(mineru_adapter.convert(self.root, file)["status"], "direct_read")

    def test_source_only_mineru_install_can_spawn_dependency_imports(self):
        package = self.root / "runtime-mineru/site-packages/mineru"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("fixture_marker = 'local-target-import'\n", encoding="utf-8")
        command = mineru_adapter.command(self.root)
        self.assertEqual(Path(command[0]).resolve(), Path(sys.executable).resolve())
        process = subprocess.run([command[0], "-c", "import mineru; print(mineru.fixture_marker)"], env=mineru_adapter.environment(self.root), capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout.strip(), "local-target-import")

    def test_incomplete_mineru_export_rejected(self):
        file = self.root / "partial.md"
        file.write_text("<!-- page 1 of 3 -->\n只有一页", encoding="utf-8")
        with self.assertRaisesRegex(ExamError, "页序不完整"):
            mineru_adapter.validate_export(file, {})


if __name__ == "__main__":
    unittest.main()
