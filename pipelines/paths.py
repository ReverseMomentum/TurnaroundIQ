from pathlib import Path
import sys


def project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "database.py").exists():
            root = candidate
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            return root
    raise RuntimeError("Could not find project root (database.py)")
