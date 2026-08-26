"""fetch_hotspots.py 回归测试：去重逻辑（纯函数，不触网）。

独立运行：python tests/test_fetch_hotspots.py
"""
import io, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import fetch_hotspots as fh

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

items = [
    {"title": " 同一热点 ", "source": "weibo", "hot": 100},
    {"title": "同一热点", "source": "toutiao", "hot": 50},
    {"title": "另一热点", "source": "baidu", "hot": 30},
    {"title": "  ", "source": "weibo", "hot": 10},
]
out = fh.deduplicate(items)
check("按标题去重", len(out) == 2, str(len(out)))
check("保留首现", out[0]["source"] == "weibo")
check("去除空白标题", all(x["title"].strip() for x in out))
check("空列表", fh.deduplicate([]) == [])

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)