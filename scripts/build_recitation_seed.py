"""Build a small, reviewed lecture starter deck from exact local source paragraphs.

Recipes contain locators only. Copyrighted lecture prose is read locally and never
embedded in public source. Source changes require reviewing these recipes again.
"""
from pathlib import Path
import argparse
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tax_exam import recitation, questions
from tax_exam.library import read_block
from tax_exam.common import ExamError


def build(root=ROOT):
    root = Path(root).resolve()

    def paragraph(block_id, prefix, stop=None):
        block = read_block(root, block_id)
        match = next((p.strip() for p in block["text"].split("\n\n") if p.strip().startswith(prefix)), None)
        if match is None:
            raise ExamError("seed_source_changed", "初始卡片原文位置变化，先复核配方，不猜测替代正文")
        if stop:
            match = match.split(stop, 1)[0].rstrip()
        return {"block_id": block_id, "quote": match}

    recipes = [
        ("ym-cn-01-law", "税收法定原则：含义与基本内容", "中国税法学", [
            ("meaning", "含义与价值", paragraph("b-d7e88bd5b281bfcc6519", "(1) 含义")),
            ("elements-legal", "课税要素法定", paragraph("b-d7e88bd5b281bfcc6519", "①课税要素法定")),
            ("elements-clear", "课税要素明确", paragraph("b-d7e88bd5b281bfcc6519", "②课税要素明确")),
            ("levy-by-law", "依法稽征", paragraph("b-d7e88bd5b281bfcc6519", "③依法稽征"))], [], "税收法定", "本卡只含讲义基础含义与三项内容；授权立法、历史评论与现行条文另行核对。"),
        ("ym-cn-02-substance", "实质课税原则：含义与适用边界", "中国税法学", [
            ("meaning", "经济观察的含义", paragraph("b-a65444fab938e22dabe4", "实质课税原则，也称")),
            ("limits", "适用范围与法定边界", paragraph("b-a65444fab938e22dabe4", "但该原则")),
            ("interpretation", "解释的边界", paragraph("b-a65444fab938e22dabe4", "因此，必须明确", " 量能深税"))], ["ym-cn-01-law"], "实质课税", "按讲义理论复述；具体案例和规则时效须另核对，不以该卡替代个案判断。"),
        ("ym-cn-03-debt", "权力关系说与债务关系说：核心区别", "中国税法学", [
            ("power", "权力关系说", paragraph("b-8048ad5785f953fe83b3", "1.权力关系说")),
            ("debt", "债务关系说", paragraph("b-8048ad5785f953fe83b3", "2.债务关系说"))], ["ym-cn-01-law"], "税收债务", "本卡是两种理论的基本主张；制度联系、程序关系及评价另卡扩展。"),
        ("ym-cn-04-income-models", "三种所得税制：定义与计税结构", "中国税法学", [
            ("classified", "分类所得税制", paragraph("b-45342c5b00166aa09805", "分类所得税制")),
            ("comprehensive", "综合所得税制", paragraph("b-b281851ad502d43c1c5b", "综合所得税制")),
            ("mixed", "分类综合所得税制", paragraph("b-a49fbbf94d6da5080934", "分类综合所得税制"))], [], "所得税制", "本卡先记三种理论模式的含义；优缺点与我国具体制度范围后续分卡学习。"),
        ("ym-int-01-jurisdiction", "税收管辖权：概念与行使边界", "国际税法学", [
            ("meaning", "管辖权的概念", paragraph("b-c5a162215c40ffed466a", "税收管辖权是一国")),
            ("sovereignty", "主权属性", paragraph("b-c5a162215c40ffed466a", "税收管辖权既然")),
            ("limits", "国际社会中的行使边界", paragraph("b-c5a162215c40ffed466a", "但是，国家"))], [], "税收管辖权", "保持讲义理论表述；协定与具体国内法边界需要结合对应章节。"),
        ("ym-int-02-residence-source", "居民与来源地管辖权：依据及有限纳税义务", "国际税法学", [
            ("resident", "居民管辖权的依据", paragraph("b-693be9c42652edc48934", "居民税收管辖权是")),
            ("source", "来源地管辖权的依据", paragraph("b-988373c7caf3ed585d57", "所得来源地税收管辖权，")),
            ("limited", "来源地管辖权下的纳税范围", paragraph("b-988373c7caf3ed585d57", "所得来源地税收管辖权之下"))], ["ym-int-01-jurisdiction"], "税收管辖权", "本卡聚焦两种依据与来源地有限义务；居民身份标准和其他范围另行学习。"),
        ("ym-int-03-double-tax", "法律意义与经济意义国际重复征税：概念辨析", "国际税法学", [
            ("legal", "法律意义的定义（讲义引2017年OECD范本）", paragraph("b-ec318dc05c3ba2a7b1e7", "2017年OECD", "根据此定义")),
            ("economic", "经济意义的定义", paragraph("b-29776a5658a605edb6f2", "经济意义的国际重复征税，", " 同一模源")),
            ("difference", "纳税主体同一性区别", paragraph("b-29776a5658a605edb6f2", "与前述法律性"))], ["ym-int-01-jurisdiction"], "重复征税", "按讲义所引2017年定义进行理论辨析；五项构成要件与具体协定应用另卡学习。"),
        ("ym-int-04-exemption", "全额免税与累进免税：概念区别", "国际税法学", [
            ("full", "全额免税法的概念", paragraph("b-e5b19dd1340418be3770", "全额免税法，", "其计算公式")),
            ("progressive", "累进免税法的概念", paragraph("b-46d1cbe9ed87b1df8ec6", "累进免税法，", "其计算公式"))], ["ym-int-02-residence-source"], "免税法", "本卡只比较境外所得是否影响境内适用税率的理论区别；完整计算与适用条件另行学习。"),
    ]
    result = []
    short_minutes = {"ym-cn-03-debt": 8, "ym-cn-04-income-models": 8, "ym-int-01-jurisdiction": 6, "ym-int-02-residence-source": 8, "ym-int-03-double-tax": 8, "ym-int-04-exemption": 6}
    true_questions = questions.list_questions(root, source_type="past_exam")
    for card_id, title, subject, points, prerequisites, term, limitation in recipes:
        result.append(recitation.save(root, {"id": card_id, "title": title, "subject": subject, "source_id": "lecture-yanming-2026", "body": "\n\n".join(ref["quote"] for _, _, ref in points),
            "memory_outline": [label for _, label, _ in points], "prompt": "请脱稿说明“" + title + "”，保留讲义中的核心结构与必要边界。", "priority": "A1", "learn_minutes": short_minutes.get(card_id, 12),
            "points": [{"id": key, "description": label, "importance": "core", "evidence": [ref]} for key, label, ref in points], "prerequisites": prerequisites, "known_limits": [limitation, "来源为2026年整理的讲义与OCR原文，未据此核验2027年现行法。"],
            "related_question_ids": [q["id"] for q in true_questions if q["subject"] == subject and term in q["stem"]][:4]}, True))
    return {"starter_cards": len(result), "full_lecture_coverage": False, "cards": result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    print(json.dumps(build(parser.parse_args().root), ensure_ascii=False))
