"""Optional real-library retrieval smoke checks; no model requests or record writes."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tax_exam import library, questions
from tax_exam.common import write_json

CASES = [
    ("税收抵免法", ["抵免"]), ("经济性重复征税", ["经济", "重复"]),
    ("常设机构", ["常设机构"]), ("无差别待遇", ["无差别"]),
    ("量能课税", ["量能"]), ("税收法定原则", ["法定"]),
    ("实质课税原则", ["实质"]), ("个人所得税", ["个人所得税"]),
    ("增值税", ["增值税"]), ("转让定价", ["定价"]),
    ("主要目的测试", ["目的"]), ("受控外国公司", ["受控", "公司"]),
    ("资本弱化", ["资本弱化"]), ("相互协商程序", ["相互协商"]),
    ("税收情报交换", ["情报交换"]), ("数字经济", ["数字"]),
    ("foreign tax credit", ["credit"]), ("permanent establishment", ["establishment"]),
    ("treaty shopping", ["shopping"]), ("transfer pricing", ["pricing"]),
]


def verify(root=ROOT):
    results = []
    for query, expected in CASES:
        blocks = library.search(root, query)["results"]
        matching = next((block for block in blocks if all(term.lower() in block["text"].lower() for term in expected)), None)
        if matching:
            library.read_block(root, matching["id"], matching["text"].strip()[:40])
        results.append({"query": query, "topic_found_in_top5": bool(matching), "evidence_id": matching["id"] if matching else None})
    summary = {"type": "topic_retrieval_smoke_not_answer_accuracy", "checks": results, "passed": sum(item["topic_found_in_top5"] for item in results), "total": len(results), "banks": questions.bank_summary(root)}
    write_json(root / ".work/material-check.json", summary)
    return summary


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(verify(), ensure_ascii=False))
