"""支持：python -m zexbot（任意当前目录下建议仍位于项目根 bot 内）。启动前补全 import 路径。"""

from __future__ import annotations

import sys
from pathlib import Path

_pkg = Path(__file__).resolve().parent
_root = _pkg.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from zexbot.main import main

if __name__ == "__main__":
    main()
