"""Portable entry point; does not require installing the Python package."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from tax_exam.cli import main

if __name__ == "__main__":
    main()
