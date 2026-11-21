"""Behavior checks use only self-authored materials and temporary projects."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from build_library import build
from tax_exam import library, questions, records
from tax_exam.common import ExamError, load_json, write_json


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        workspace = ROOT / ".work/tests"
        workspace.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=workspace)
        self.root = Path(self.temp.name) / "中文 项目"
        self.root.mkdir()
        build(self.root, demo=True)
        self.bank = ROOT / "examples/demo-bank.json"
        questions.import_bank(self.root, self.bank, True)
        self.question_id = "demo-library:quota"
        self.now = datetime(2026, 11, 10, 20, 0, tzinfo=timezone(timedelta(hours=8)))

    def tearDown(self):
        assert Path(self.temp.name).resolve().is_relative_to((ROOT / ".work/tests").resolve())
        self.temp.cleanup()

    def evidence(self):
        result = library.search(self.root, "借阅额度")["results"]
        block = next(item for item in result if "同时最多借阅三本书" in item["text"])
        return [{"block_id": block["id"], "quote": "每张阅读卡同时最多借阅三本书。"}]

    def attempt(self, now=None, **fields):
        data = {"kind": "attempt", "question_id": self.question_id, "answer": "不能，因为尚未登记。", **fields}
        return records.save_event(self.root, data, now or self.now)["event"]

    def feedback(self, attempt, now=None, **fields):
        return records.save_event(self.root, {"kind": "feedback", "target_id": attempt["id"], "assessment": "independent", "feedback": "原理覆盖；后续还需换情境验证。", "evidence": self.evidence(), "knowledge_points": ["借阅额度"], **fields}, now or self.now, allow_legacy=True)["event"]

    def test_search_returns_exact_source_and_verifiable_quote(self):
        evidence = self.evidence()[0]
        block = library.read_block(self.root, evidence["block_id"], evidence["quote"])
        source = (self.root / block["path"]).read_text(encoding="utf-8")
        self.assertEqual(source[block["start"]:block["end"]], block["text"])
        self.assertEqual(block["pdf_page_start"], 1)
        with self.assertRaisesRegex(ExamError, "引文"):
            library.read_block(self.root, block["id"], "教材里没有这句话")

    def test_changed_source_invalidates_evidence(self):
        evidence = self.evidence()[0]
        source = library.manifest(self.root)["sources"][0]
        with (self.root / source["path"]).open("a", encoding="utf-8") as stream:
            stream.write("\n修改正文")
        with self.assertRaisesRegex(ExamError, "资料已变更"):
            library.read_block(self.root, evidence["block_id"])

    def test_answer_is_opt_in(self):
        question = questions.get_question(self.root, self.question_id)
        self.assertNotIn("answer", question)
        self.assertNotIn("answer", questions.list_questions(self.root)[0])
        self.assertIn("不能", questions.get_question(self.root, self.question_id, True)["answer"]["text"])

    def test_import_preview_no_mutation_and_deduplication(self):
        data = load_json(self.bank)
        data["id"] = "second-bank"
        file = self.root / "new.json"
        write_json(file, data)
        preview = questions.import_bank(self.root, file)
        self.assertEqual(preview["duplicates"], ["quota"])
        self.assertFalse((self.root / "userdata/imported-banks/second-bank.json").exists())
        questions.import_bank(self.root, file, True)
        self.assertEqual(len(questions.all_banks(self.root)), 2)

    def test_ai_question_requires_real_evidence_and_no_exam_year(self):
        data = load_json(self.bank)
        data.update(id="generated", source_type="ai_generated")
        with self.assertRaises(ExamError):
            questions.validate_bank(data)
        data["questions"][0]["evidence"] = self.evidence()
        data["questions"][0]["year"] = 2027
        with self.assertRaises(ExamError):
            questions.validate_bank(data)
        del data["questions"][0]["year"]
        file = self.root / "ai.json"
        write_json(file, data)
        questions.import_bank(self.root, file, True)

    def test_markdown_bank_import_preserves_context_and_hides_answer(self):
        result = questions.import_markdown(self.root, ROOT / "examples/demo-bank.md", "md-example", "演示题库", "演示科目", "custom", True)
        self.assertEqual(result["count"], 1)
        question = questions.get_question(self.root, "md-example:quota-md")
        self.assertEqual(question["context"], "自制演示书屋规定：归还登记完成后才释放借阅额度。")
        self.assertNotIn("answer", question)

    def test_daily_append_preserves_manual_notes(self):
        attempt = self.attempt()
        file = self.root / "userdata/study-records/2026-11-10.md"
        with file.open("a", encoding="utf-8") as stream:
            stream.write("\n## 我的手工笔记\n记得核对教材限制条件。\n")
        self.feedback(attempt)
        self.assertIn("我的手工笔记", file.read_text(encoding="utf-8"))
        self.assertEqual(len(records.read_events(self.root)), 2)
        self.assertEqual(len(list((self.root / "userdata/study-records").glob("*.md"))), 1)
        self.assertTrue((self.root / "userdata/backups/2026-11-10.md.previous").exists())

    def test_review_restores_after_cache_removal_and_cancel(self):
        feedback = self.feedback(self.attempt())
        shutil.rmtree(self.root / "indexes")
        states = records.review_state(self.root, "2026-11-11")
        self.assertTrue(states[0]["due"])
        self.assertEqual(states[0]["independent_days"], 1)
        records.save_event(self.root, {"kind": "cancel", "target_id": feedback["id"]}, self.now)
        self.assertEqual(records.review_state(self.root), [])

    def test_hints_cannot_be_marked_independent(self):
        attempt = self.attempt(hints_used=True)
        with self.assertRaisesRegex(ExamError, "提示"):
            self.feedback(attempt)
        event = self.feedback(attempt, assessment="hinted")
        self.assertEqual(event["next_review"], "2026-11-11")

    def test_idempotent_request_and_conflicting_retry(self):
        data = {"kind": "note", "text": "记录今天学习", "request_id": "same-request"}
        first = records.save_event(self.root, data, self.now)
        second = records.save_event(self.root, data, self.now)
        self.assertEqual(first["event"]["id"], second["event"]["id"])
        with self.assertRaisesRegex(ExamError, "不同内容"):
            records.save_event(self.root, {**data, "text": "不同的笔记"}, self.now)
        self.assertEqual(len(records.read_events(self.root)), 1)

    def test_concurrent_append_does_not_lose_notes(self):
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda n: records.save_event(self.root, {"kind": "note", "text": f"笔记{n}"}, self.now), range(8)))
        self.assertEqual(len(records.read_events(self.root)), 8)

    def test_same_day_retries_do_not_inflate_review_interval(self):
        self.feedback(self.attempt())
        event = self.feedback(self.attempt())
        self.assertEqual(event["next_review"], "2026-11-11")
        next_day = self.now + timedelta(days=1)
        next_event = self.feedback(self.attempt(next_day), next_day)
        self.assertEqual(next_event["next_review"], "2026-11-14")

    def test_handwritten_outside_event_survives_and_damaged_json_fails(self):
        self.attempt()
        file = self.root / "userdata/study-records/2026-11-10.md"
        text = file.read_text(encoding="utf-8")
        file.write_text(text.replace('"schema_version": 1', '"schema_version": 99'), encoding="utf-8")
        with self.assertRaisesRegex(ExamError, "无法读取"):
            records.read_events(self.root)
        with self.assertRaises(ExamError):
            records.save_event(self.root, {"kind": "note", "text": "不可覆盖损坏文件"}, self.now)

    def test_cli_works_after_moving_and_uses_utf8(self):
        destination = Path(self.temp.name) / "移动 项目"
        self.assertTrue(destination.resolve().is_relative_to((ROOT / ".work/tests").resolve()))
        self.assertTrue(self.root.resolve().is_relative_to((ROOT / ".work/tests").resolve()))
        self.root.rename(destination)
        output = subprocess.run([sys.executable, str(ROOT / "tax_exam.py"), "--root", str(destination), "questions"], capture_output=True, encoding="utf-8", check=True)
        data = json.loads(output.stdout)
        self.assertTrue(data["ok"])
        self.assertIn("阅读卡", data["data"]["questions"][0]["stem"])


class ParsingTest(unittest.TestCase):
    def test_case_subquestions_and_treaty_articles_do_not_mix(self):
        text = """# 演示题
## 国际税法学
### 四、案例分析（回忆版）
现有以下条件：
（1）甲公司持有乙公司股份。
（2）甲向乙发放贷款。
问题:
（1）贷款如何分析？
（2）是否存在关联关系？
#### 题目附带条文
1. Article one text.
2. Article two text.
"""
        parsed = questions.parse_exam(text, 2026, "exam")
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["stem"], "贷款如何分析？")
        self.assertIn("甲向乙发放贷款", parsed[0]["context"])
        self.assertIn("Article one text", parsed[0]["context"])

    def test_missing_other_question_does_not_disable_visible_term(self):
        text = "# 演示题\n## 中国税法学｜名词解释\n> 第5题未提供\n\n### 第1题：演示概念\n"
        result = questions.parse_exam(text, 2024, "exam")
        self.assertEqual(result[0]["completeness"], "complete")

    def test_cross_page_block_retains_exact_offsets(self):
        text = "<!-- page 1 of 2 -->\n\n## 定义\n\n概念在本页开始。\n\n<!-- page 2 of 2 -->\n\n限制条件延续到下一页。\n"
        source = {"id": "demo", "sha256": "hash", "path": "demo.md", "title": "demo", "role": "textbook"}
        blocks = list(library.chunks(text, source))
        block = next(item for item in blocks if "概念" in item["text"])
        self.assertIn("限制条件", block["text"])
        self.assertEqual(block["pdf_page_end"], 2)
        self.assertEqual(text[block["start"]:block["end"]], block["text"])


if __name__ == "__main__":
    unittest.main()
