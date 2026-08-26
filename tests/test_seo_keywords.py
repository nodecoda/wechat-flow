"""seo_keywords.py 回归测试：关键词分析（mock 建议源）。

独立运行：python tests/test_seo_keywords.py
"""
import io, sys
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import seo_keywords as sk

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

class FakeResp:
    def __init__(self, data): self._d = data
    def json(self): return self._d

# mock 两个建议源：baidu 3 条、so360 2 条
baidu = ["AI写作", "AI写作工具", "AI写作软件"]
so360 = {"result": [{"word": "AI写作"}, {"word": "AI写作教程"}]}
with mock.patch.object(sk.requests, "get", side_effect=[
    FakeResp(["q", baidu]), FakeResp(so360),  # baidu=[query, sugs]；so360={"result":[...]}
]):
    r = sk.analyze_keyword("AI写作")
    check("seo_score = (3+2)/2", r["seo_score"] == 2.5, str(r["seo_score"]))
    check("baidu_score=3", r["baidu_score"] == 3)
    check("so360_score=2", r["so360_score"] == 2)
    check("related 去重=4", len(r["related_keywords"]) == 4, str(r["related_keywords"]))

# 源失败 → 空建议 + 分数 0，不抛异常
with mock.patch.object(sk.requests, "get", side_effect=Exception("timeout")):
    r2 = sk.analyze_keyword("x")
    check("源失败降级 0 分", r2["seo_score"] == 0, str(r2["seo_score"]))
    check("源失败不抛异常", r2["baidu_suggestions"] == [])

# baidu_suggestions 解析 [query, [sug...]]
with mock.patch.object(sk.requests, "get", return_value=FakeResp(["q", ["a", "b", "c"]])):
    check("baidu_suggestions 解析", sk.baidu_suggestions("k") == ["a", "b", "c"])

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)