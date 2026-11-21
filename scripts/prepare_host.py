"""Generate the documented DeepSeek Harness project skill location."""
from pathlib import Path
import argparse
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tax_exam.common import inside


def prepare(root):
    root = Path(root).resolve()
    target = inside(root, ".dsh/skills")
    for source in inside(root, "skills").iterdir():
        if source.is_dir() and (source / "SKILL.md").is_file():
            shutil.copytree(source, target / source.name, dirs_exist_ok=True)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(prepare(args.root))
