"""Source-tree wrapper for the optional local catalog UI, never default BSL mode."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from yadinassi.ui.local_app import main

if __name__ == '__main__': raise SystemExit(main())
