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

# ---- fetcher 解析（mock 网络） ----
import json as _json
from unittest import mock

class FakeResp:
    def __init__(self, data): self._d = data
    def json(self): return self._d

# weibo
with mock.patch.object(fh.requests, "get", return_value=FakeResp(
    {"data": {"realtime": [{"note": "热点A", "num": 100, "label_name": "热"}, {"note": "", "num": 5}]}}
)):
    items = fh.fetch_weibo()
    check("weibo 解析", len(items) == 1 and items[0]["title"] == "热点A" and items[0]["hot"] == 100)

# toutiao
with mock.patch.object(fh.requests, "get", return_value=FakeResp(
    {"data": [{"Title": "T1", "HotValue": "200", "Url": "https://x/1"}, {"Title": "", "HotValue": 0}]}
)):
    items = fh.fetch_toutiao()
    check("toutiao 解析", len(items) == 1 and items[0]["hot"] == 200)

# baidu（cards 嵌套结构）
with mock.patch.object(fh.requests, "get", return_value=FakeResp(
    {"data": {"cards": [{"content": [{"content": [{"word": "热词1", "hotScore": "300"}]}]}]}}
)):
    items = fh.fetch_baidu()
    check("baidu 解析嵌套", len(items) == 1 and items[0]["title"] == "热词1" and items[0]["hot"] == 300)

# 网络异常 → 空列表 + 不抛异常
with mock.patch.object(fh.requests, "get", side_effect=Exception("net down")):
    check("weibo 异常降级", fh.fetch_weibo() == [])
    check("toutiao 异常降级", fh.fetch_toutiao() == [])
    check("baidu 异常降级", fh.fetch_baidu() == [])

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)