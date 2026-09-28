#!/usr/bin/env python3
"""UserPromptSubmit hook: point batch-image requests at the plugin commands. Advisory only."""
from __future__ import annotations

import json
import re
import sys

INTENT_RE = re.compile(r"批量出图|批量生成图|图片工厂|image\s*factory|成批出图|出图任务", re.IGNORECASE)

def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        # Malformed hook stdin is advisory-only: degrade to no hint, never crash.
        payload = {}
    prompt = str(payload.get("prompt") or "") if isinstance(payload, dict) else ""
    if prompt.strip().startswith("/"):
        return 0
    if INTENT_RE.search(prompt):
        print("提示：该请求疑似批量出图相关。可用 /image-factory 总入口或细分命令 (/image-factory-run /image-factory-judge /image-factory-recover)。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
