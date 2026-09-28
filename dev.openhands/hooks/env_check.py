#!/usr/bin/env python3
"""SessionStart hook: report Image Factory readiness. Advisory only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    lines = [f"python3: {sys.version.split()[0]}"]
    cli = ROOT / "scripts" / "image_factory_cli.py"
    if not cli.is_file():
        cands = sorted((ROOT / "scripts").glob("*.py")) if (ROOT / "scripts").is_dir() else []
        lines.append(f"scripts: {len(cands)} 个模块" + ("（入口以 image-factory-use 技能为准）" if cands else "缺失"))
    else:
        lines.append("factory CLI: 就绪")
    lines.append("出图凭据: 按技能指引配置（配额与计费由服务端管）")
    # Drain the hook payload so the host never sees a broken pipe; advisory only.
    try:
        sys.stdin.read()
    except (OSError, ValueError):
        pass
    print("图片工厂插件环境：" + "；".join(lines))
    return 0

if __name__ == "__main__":
    # Validate only; the payload itself is unused at SessionStart.
    try:
        json.load(sys.stdin)
    except (ValueError, OSError):
        pass
    sys.exit(main())
