"""Entry point for the separately prepared, project-local MinerU dependencies."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(ROOT / "runtime-mineru/site-packages"))
os.environ.setdefault("MINERU_HOME", str(ROOT / "userdata/mineru"))
os.environ.setdefault("MINERU_TELEMETRY_DISABLED", "1")
from mineru.cli.main import main

if __name__ == "__main__":
    main()
