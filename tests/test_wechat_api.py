"""wechat_api.py 回归测试：token 缓存/错误与 content-type（mock 网络）。

独立运行：python tests/test_wechat_api.py
"""
import io, sys, time
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "toolkit"))

import wechat_api as wa

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

# ---- _guess_content_type ----
check("content-type jpg", wa._guess_content_type("a.jpg").startswith("image/jpeg"))
check("content-type png", wa._guess_content_type("a.png").startswith("image/png"))
check("content-type 未知→octet-stream", wa._guess_content_type("a.xyz") == "application/octet-stream")

# ---- get_access_token ----
class FakeResp:
    def __init__(self, data): self._d = data
    def json(self): return self._d

# 成功 + 缓存（第二次不触网）
wa._token_cache.clear()
calls = {"n": 0}
def fake_get(url, **kw):
    calls["n"] += 1
    return FakeResp({"access_token": "TOK_1", "expires_in": 7200})

with mock.patch.object(wa.requests, "get", side_effect=fake_get):
    t1 = wa.get_access_token("app1", "secret1")
    check("首次取 token", t1 == "TOK_1")
    t2 = wa.get_access_token("app1", "secret1")
    check("缓存命中不触网", calls["n"] == 1 and t2 == "TOK_1")
    t3 = wa.get_access_token("app1", "secret1", force_refresh=True)
    check("force_refresh 重新请求", calls["n"] == 2 and t3 == "TOK_1")

# API 错误 → ValueError
with mock.patch.object(wa.requests, "get", return_value=FakeResp({"errcode": 40013, "errmsg": "invalid appid"})):
    try:
        wa.get_access_token("bad", "bad")
        check("错误码抛 ValueError", False)
    except ValueError as e:
        check("错误码抛 ValueError", "40013" in str(e))

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)