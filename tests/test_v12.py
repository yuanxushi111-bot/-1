"""Behavioral checks using self-authored library material, never real student data."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tax_exam import daily, feedback, library, materials, mistakes, questions, recitation, records, selftests
from tax_exam.common import ExamError, write_json


class DailyStudyTest(unittest.TestCase):
    def setUp(self):
        base = ROOT / ".work/tests-v12"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 11, 13, 20, 0, tzinfo=timezone(timedelta(hours=8)))
        materials.build_library(self.root, demo=True)
        write_json(self.root / "userdata/study-settings.json", {"main_source_id": "demo-book"})
        block = next(b for b in library.search(self.root, "归还登记")["results"] if "完成归还登记后释放" in b["text"])
        self.refs = [{"block_id": block["id"], "quote": "完成归还登记后释放一个借阅额度"}, {"block_id": block["id"], "quote": "仅把书放进归还箱而没有登记时，不视为完成归还"}]
        self.payload = {"id": "card-a", "title": "自制归还登记卡", "subject": "演示科目", "source_id": "demo-book", "body": "完成归还登记后释放一个借阅额度；仅把书放进归还箱而没有登记时，不视为完成归还。", "memory_outline": ["完成登记", "投箱不等于登记"], "prompt": "请说明归还额度释放条件及投箱情形。", "learn_minutes": 12,
                        "points": [{"id": "register", "description": "登记条件", "evidence": [self.refs[0]]}, {"id": "box", "description": "投箱情形", "evidence": [self.refs[1]]}]}
        recitation.save(self.root, self.payload, True)
        other = {**self.payload, "id": "card-b", "title": "第二张未学习卡", "prerequisites": ["card-a"]}
        recitation.save(self.root, other, True)

    def tearDown(self):
        assert self.root.resolve().is_relative_to((ROOT / ".work/tests-v12").resolve())
        self.temp.cleanup()

    def learn(self, now=None, key="card-a"):
        return recitation.view(self.root, key, complete=True, now=now or self.now)

    def qid(self, key="card-a"):
        return recitation.view(self.root, key)["question_id"]

    def grade(self, status="covered", now=None, qid=None):
        when = now or self.now
        attempt = records.save_event(self.root, {"kind": "attempt", "question_id": qid or self.qid(), "answer": self.payload["body"], "hints_used": False}, when)["event"]
        context = feedback.answer_context(self.root, attempt)
        results = [{"point_id": p["id"], "status": status, "student_quote": None if status in {"missing", "uncertain"} else attempt["answer"], "reason": "对照自制材料核对必要条件。"} for p in context["question"]["rubric"]["items"]]
        return records.save_event(self.root, {"kind": "feedback", "target_id": attempt["id"], "point_results": results}, when)

    def test_no_time_does_not_silently_borrow_yesterday(self):
        with self.assertRaisesRegex(ExamError, "多久"):
            daily.today(self.root, now=self.now)
        daily.today(self.root, minutes=30, now=self.now)
        with self.assertRaises(ExamError):
            daily.today(self.root, now=self.now + timedelta(days=1))

    def test_time_budgets_and_prerequisites(self):
        for minutes in (10, 30, 60):
            p = daily.today(self.root, minutes=minutes, revise=True, now=self.now)
            self.assertLessEqual(p["pending_estimated_minutes"], minutes)
            self.assertFalse(any(t.get("card_id") == "card-b" for t in p["tasks"]))
        self.assertTrue(any(t["kind"] == "learn" for t in p["tasks"]))

    def test_short_first_day_can_learn_one_small_card_without_forcing_test(self):
        recitation.save(self.root, {**self.payload, "id": "card-short", "title": "自制小主题", "learn_minutes": 6}, True)
        p = daily.today(self.root, minutes=10, now=self.now)
        self.assertTrue(any(t["kind"] == "learn" and t["card_id"] == "card-short" for t in p["tasks"]))
        self.assertFalse(any(t["kind"] == "self_test" for t in p["tasks"]))

    def test_same_day_reopen_is_stable_and_manual_notes_survive(self):
        p = daily.today(self.root, minutes=30, now=self.now)
        file = self.root / p["path"]
        file.write_text(file.read_text(encoding="utf-8") + "\n我的工作安排：今天提前结束。\n", encoding="utf-8")
        again = daily.today(self.root, now=self.now)
        self.assertEqual(p["tasks"], again["tasks"])
        self.assertEqual(len(daily.snapshots(self.root, self.now.date().isoformat())), 1)
        daily.today(self.root, remaining=10, now=self.now)
        self.assertIn("我的工作安排", file.read_text(encoding="utf-8"))

    def test_rebudget_retains_completed_work(self):
        p = daily.today(self.root, minutes=30, now=self.now)
        self.learn()
        revised = daily.today(self.root, remaining=10, now=self.now)
        self.assertLessEqual(revised["pending_estimated_minutes"], 10)
        self.assertTrue(any(t["id"] in {v["id"] for v in p["tasks"]} and t["kind"] == "learn" and t["status"] == "已完成" for t in revised["tasks"]))

    def test_metadata_read_does_not_claim_seen_or_learned(self):
        closed = recitation.view(self.root, "card-a")
        self.assertNotIn("body", closed)
        self.assertEqual(records.read_events(self.root), [])
        self.assertEqual(recitation.progress(self.root, self.now)[0]["status"], "未学习")

    def test_self_report_is_not_a_pass_and_makes_next_day_due(self):
        self.learn()
        p = recitation.progress(self.root, self.now)[0]
        self.assertEqual(p["status"], "已学习")
        self.assertEqual(p["independent_pass_days"], [])
        self.assertTrue(recitation.progress(self.root, self.now + timedelta(days=1))[0]["due"])

    def test_study_idempotency(self):
        recitation.view(self.root, "card-a", complete=True, now=self.now, request_id="learn-once")
        again = recitation.view(self.root, "card-a", complete=True, now=self.now, request_id="learn-once")
        self.assertTrue(again["record"]["duplicate_request"])
        self.assertEqual(len(records.read_events(self.root)), 1)

    def test_cancel_learning_claim_reopens_task_without_unseeing_body(self):
        p = daily.today(self.root, minutes=30, now=self.now)
        result = self.learn()
        records.save_event(self.root, {"kind": "cancel", "target_id": result["record"]["event"]["id"], "text": "刚才误报背完"}, self.now)
        self.assertEqual(recitation.progress(self.root, self.now)[0]["status"], "未学习")
        self.assertFalse(any(t["kind"] == "learn" and t["status"] == "已完成" for t in daily.project(self.root, p)["tasks"]))
        with self.assertRaises(ExamError):
            selftests.studied_cards(self.root, self.now)
        self.assertEqual(self.grade()["event"]["assessment"], "hinted")

    def test_skipped_then_actually_completed_learning_shows_completed(self):
        p = daily.today(self.root, minutes=30, now=self.now)
        task = next(t for t in p["tasks"] if t["kind"] == "learn")
        records.save_event(self.root, {"kind": "study", "action": "skipped", "task_id": task["id"]}, self.now)
        self.assertEqual(daily.task_state(self.root, task, p["date"]), "已跳过")
        self.learn()
        self.assertEqual(daily.task_state(self.root, task, p["date"]), "已完成")

    def test_planned_but_unlearned_cards_are_not_test_scope(self):
        daily.today(self.root, minutes=30, now=self.now)
        with self.assertRaisesRegex(ExamError, "还没有"):
            selftests.create(self.root, now=self.now)
        self.learn()
        context = selftests.context(self.root, self.now)
        self.assertEqual([c["id"] for c in context["cards"]], ["card-a"])

    def test_yesterday_card_not_silently_in_today_scope(self):
        self.learn()
        with self.assertRaises(ExamError):
            selftests.studied_cards(self.root, self.now + timedelta(days=1))
        self.assertEqual(len(selftests.studied_cards(self.root, self.now + timedelta(days=1), include_due=True)), 1)

    def test_default_generation_hides_answer_rubric_and_quotes(self):
        daily.today(self.root, minutes=30, now=self.now)
        self.learn()
        generated = selftests.create(self.root, count=2, now=self.now)
        self.assertEqual(generated["generated_count"], 1)
        question = generated["next"]["question"]
        for key in ("answer", "rubric", "evidence", "body", "memory_outline"):
            self.assertNotIn(key, question)
        self.assertIn("card_refs", question)
        self.assertNotIn("point_ids", question["card_refs"][0])
        self.assertEqual(selftests.create(self.root, now=self.now)["set_id"], generated["set_id"])
        self.assertEqual(len(selftests.sets(self.root)), 1)

    def test_same_day_body_exposure_cannot_be_overridden(self):
        recitation.view(self.root, "card-a", learn=True, now=self.now)
        result = self.grade()
        self.assertEqual(result["event"]["assessment"], "hinted")
        self.assertEqual(recitation.progress(self.root, self.now)[0]["independent_pass_days"], [])

    def test_self_test_feedback_uses_frozen_key_and_flows_to_mistakes(self):
        daily.today(self.root, minutes=30, now=self.now)
        self.learn()
        generated = selftests.create(self.root, now=self.now)
        q = generated["next"]["question"]
        result = self.grade("missing", qid=q["id"])
        self.assertIn(self.payload["body"], result["rendered_feedback"])
        self.assertTrue(result["mistake_book"]["updated"])
        self.assertEqual(mistakes.list_mistakes(self.root)[0]["error_count"], 1)
        self.assertTrue(selftests.next_question(self.root, now=self.now)["completed"])
        self.assertEqual(result["event"]["card_refs"][0]["id"], "card-a")

    def test_frozen_rubric_cannot_be_changed_after_answer(self):
        a = records.save_event(self.root, {"kind": "attempt", "question_id": self.qid(), "answer": self.payload["body"]}, self.now)["event"]
        original = feedback.answer_context(self.root, a)["question"]["rubric"]
        changed = copy.deepcopy(original)
        changed["items"][0]["importance"] = "supplement"
        with self.assertRaisesRegex(ExamError, "已经固定"):
            records.save_event(self.root, {"kind": "feedback", "target_id": a["id"], "rubric": changed, "point_results": []}, self.now)

    def test_two_cross_day_passes_and_cancel_recompute_progress(self):
        self.learn()
        self.grade("missing", self.now + timedelta(days=1))
        self.grade("covered", self.now + timedelta(days=2))
        last = self.grade("covered", self.now + timedelta(days=3))
        self.assertEqual(recitation.progress(self.root, self.now + timedelta(days=3))[0]["status"], "已巩固")
        records.save_event(self.root, {"kind": "cancel", "target_id": last["event"]["id"]}, self.now + timedelta(days=3))
        self.assertEqual(recitation.progress(self.root, self.now + timedelta(days=3))[0]["status"], "复测中")

    def test_one_tested_point_does_not_pass_whole_card(self):
        self.learn()
        tomorrow = self.now + timedelta(days=1)
        daily.today(self.root, minutes=30, now=tomorrow)
        draft = {"questions": [{"card_id": "card-a", "card_version": recitation.load(self.root, "card-a")["version"], "point_ids": ["register"], "kind": "简答", "stem": "说明登记的作用。", "answer": self.refs[0]["quote"]}]}
        generated = selftests.create(self.root, draft=draft, now=tomorrow, include_due=True)
        self.grade(now=tomorrow, qid=generated["next"]["question"]["id"])
        p = recitation.progress(self.root, tomorrow)[0]
        self.assertEqual(p["independent_pass_days"], [])
        self.assertIn("box", p["unmeasured_points"])

    def test_imported_question_cannot_reference_unlearned_or_nonexistent_points(self):
        daily.today(self.root, minutes=30, now=self.now)
        self.learn()
        draft = {"questions": [{"card_id": "card-b", "card_version": recitation.load(self.root, "card-b")["version"], "point_ids": ["register"], "kind": "简答", "stem": "范围外", "answer": "不应接受"}]}
        with self.assertRaisesRegex(ExamError, "实际背过"):
            selftests.create(self.root, draft=draft, now=self.now)
        draft["questions"][0].update(card_id="card-a", card_version=recitation.load(self.root, "card-a")["version"], point_ids=["invented"])
        with self.assertRaisesRegex(ExamError, "考查要点"):
            selftests.create(self.root, draft=draft, now=self.now)

    def test_imported_variants_consume_existing_budget(self):
        daily.today(self.root, minutes=30, now=self.now)
        self.learn()
        card = recitation.load(self.root, "card-a")
        draft = {"questions": [{"card_id": card["id"], "card_version": card["version"], "point_ids": ["register"], "kind": "其他", "stem": f"自制判断题{i}，请说明理由。", "answer": self.refs[0]["quote"]} for i in range(2)]}
        selftests.create(self.root, draft=draft, now=self.now)
        with self.assertRaisesRegex(ExamError, "预算已分配"):
            selftests.create(self.root, new=True, now=self.now)
        retry = selftests.create(self.root, draft=draft, now=self.now)
        self.assertTrue(retry["reused"])
        self.assertEqual(len(selftests.sets(self.root)), 1)

    def test_remaining_budget_carries_only_affordable_existing_questions(self):
        daily.today(self.root, minutes=30, now=self.now)
        self.learn()
        card = recitation.load(self.root, "card-a")
        draft = {"questions": [{"card_id": card["id"], "card_version": card["version"], "point_ids": ["register"], "kind": "简答", "stem": f"自制小问{i}", "answer": self.refs[0]["quote"]} for i in range(2)]}
        generated = selftests.create(self.root, draft=draft, now=self.now)
        revised = daily.today(self.root, remaining=5, now=self.now)
        self.assertLessEqual(revised["pending_estimated_minutes"], 5)
        carry = next(t for t in revised["tasks"] if t.get("question_ids"))
        self.assertEqual(len(carry["question_ids"]), 1)
        self.grade("missing", qid=selftests.next_question(self.root, now=self.now)["question"]["id"])
        nxt = selftests.next_question(self.root, now=self.now)
        self.assertFalse(nxt["completed"])
        self.assertTrue(nxt["budget_complete"])
        daily.today(self.root, remaining=10, now=self.now)
        nxt = selftests.next_question(self.root, now=self.now)
        self.assertEqual(nxt["question"]["id"], generated["set_id"] + ":q-2")

    def test_no_affordable_pending_question_is_not_served_outside_budget(self):
        self.learn()
        tomorrow = self.now + timedelta(days=1)
        daily.today(self.root, minutes=30, now=tomorrow)
        selftests.create(self.root, now=tomorrow, include_due=True)
        p = daily.today(self.root, remaining=5, now=tomorrow)
        self.assertFalse(any(t.get("question_ids") for t in p["tasks"]))
        nxt = selftests.next_question(self.root, now=tomorrow)
        self.assertTrue(nxt["budget_complete"])
        self.assertNotIn("question", nxt)

    def test_completed_first_question_does_not_erase_unused_test_budget(self):
        daily.today(self.root, minutes=30, now=self.now)
        self.learn()
        generated = selftests.create(self.root, count=1, now=self.now)
        self.grade("missing", qid=generated["next"]["question"]["id"])
        self.assertEqual(selftests.context(self.root, self.now)["remaining_question_slots"], 1)

    def test_uncertain_self_test_stays_pending_verification(self):
        daily.today(self.root, minutes=30, now=self.now)
        self.learn()
        generated = selftests.create(self.root, now=self.now)
        self.grade("uncertain", qid=generated["next"]["question"]["id"])
        nxt = selftests.next_question(self.root, now=self.now)
        self.assertFalse(nxt["completed"])
        self.assertTrue(nxt["pending_verification"])

    def test_linked_real_question_retains_same_day_learning_background(self):
        questions.import_bank(self.root, ROOT / "examples/demo-bank.json", True)
        recitation.save(self.root, {**self.payload, "related_question_ids": ["demo-library:quota"]}, True)
        self.learn()
        attempt = records.save_event(self.root, {"kind": "attempt", "question_id": "demo-library:quota", "answer": self.payload["body"], "answer_seen": False}, self.now)["event"]
        self.assertTrue(attempt["answer_seen"])
        self.assertNotIn("card_refs", attempt["question_snapshot"])

    def test_generic_import_cannot_bypass_daily_scope(self):
        bank = {"schema_version": 1, "id": "fake-daily", "name": "软件样本", "source_type": "ai_generated", "version": "v1", "questions": [{"id": "q1", "subject": "演示", "kind": "简答", "stem": "软件样本题", "evidence": [self.refs[0]], "practice_kind": "daily_self_test", "card_refs": [{"id": "card-b"}]}]}
        with self.assertRaisesRegex(ExamError, "已背范围"):
            questions.import_bank(self.root, bank, True)

    def test_next_waits_for_feedback_and_cancellation_reopens_question(self):
        daily.today(self.root, minutes=30, now=self.now)
        self.learn()
        generated = selftests.create(self.root, now=self.now)
        qid = generated["next"]["question"]["id"]
        a = records.save_event(self.root, {"kind": "attempt", "question_id": qid, "answer": "不会"}, self.now)["event"]
        self.assertEqual(selftests.next_question(self.root, now=self.now)["awaiting_feedback_attempt"], a["id"])
        result = self.grade("missing", qid=qid)
        records.save_event(self.root, {"kind": "cancel", "target_id": result["event"]["id"]}, self.now)
        self.assertFalse(selftests.next_question(self.root, now=self.now)["completed"])

    def test_card_revisions_preserve_old_question_and_reset_current_progress(self):
        self.learn()
        old = recitation.load(self.root, "card-a")
        old_qid = self.qid()
        changed = {**self.payload, "memory_outline": ["调整后的记忆顺序", "登记条件"]}
        recitation.save(self.root, changed, True)
        self.assertNotEqual(old["version"], recitation.load(self.root, "card-a")["version"])
        self.assertEqual(questions.get_question(self.root, old_qid, True)["answer"]["text"], old["body"])
        self.assertEqual(recitation.progress(self.root, self.now)[0]["status"], "未学习")

    def test_modified_card_file_is_not_silently_rewritten(self):
        entry = recitation.catalog(self.root)["files"][0]
        file = self.root / entry["path"]
        file.write_text(file.read_text(encoding="utf-8") + "手改", encoding="utf-8")
        with self.assertRaisesRegex(ExamError, "直接修改"):
            recitation.load(self.root, entry["id"])

    def test_same_day_manual_pass_of_test_task_is_rejected(self):
        p = daily.today(self.root, minutes=30, now=self.now)
        task = next(t for t in p["tasks"] if t["kind"] == "self_test")
        with self.assertRaisesRegex(ExamError, "真实作答"):
            records.save_event(self.root, {"kind": "study", "action": "task_done", "task_id": task["id"]}, self.now)

    def test_few_days_absent_do_not_copy_a_backlog_into_today(self):
        daily.today(self.root, minutes=30, now=self.now)
        p = daily.today(self.root, minutes=10, now=self.now + timedelta(days=4))
        self.assertLessEqual(p["pending_estimated_minutes"], 10)
        self.assertEqual(records.read_events(self.root), [])

    def test_source_change_marks_cards_pending_verification(self):
        incoming = self.root / "incoming.md"
        incoming.write_text("# 自制新版本\n\n原文已变化。", encoding="utf-8")
        materials.import_material(self.root, incoming, source_id="demo-book", apply=True)
        p = recitation.progress(self.root, self.now)[0]
        self.assertEqual(p["status"], "待核实")
        with self.assertRaisesRegex(ExamError, "讲义版本变化"):
            self.learn()


if __name__ == "__main__":
    unittest.main()
