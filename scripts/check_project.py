"""Keyless repository checks, excluding real materials and user records."""
from pathlib import Path
import ast
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tax_exam.questions import validate_bank


def check():
    for folder in ("src", "scripts", "tests"):
        for path in (ROOT / folder).rglob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for folder in ("schemas", "config", "examples"):
        for path in (ROOT / folder).rglob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))
    for folder in (ROOT / "skills").iterdir():
        if not folder.is_dir():
            continue
        skill = (folder / "SKILL.md").read_text(encoding="utf-8")
        if not re.match(r"---\nname: " + re.escape(folder.name) + r"\ndescription: .+\n---", skill):
            raise ValueError("Skill frontmatter 无效")
        for filename in re.findall(r"\]\((references/[^)]+)\)", skill):
            if not (folder / filename).is_file():
                raise ValueError("Skill reference 不存在")
    validate_bank(json.loads((ROOT / "examples/demo-bank.json").read_text(encoding="utf-8")))
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, check=True)
    print("Repository checks passed; no real model credentials used.")


if __name__ == "__main__":
    check()
