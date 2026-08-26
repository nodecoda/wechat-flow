"""publisher.py 回归测试：HTML→纯文本与草稿 payload（mock 网络）。

独立运行：python tests/test_publisher.py
"""
import io, sys
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "toolkit"))

import publisher as pub

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

# ---- html_to_plaintext ----
html = """<section><h2>标题</h2><p>第一段。<b>加粗</b>文字。</p>
<script>var x=1;</script><style>.a{}</style>
<div>第二段 &amp; 符号</div></section>"""
pt = pub.html_to_plaintext(html)
check("去标签", "<" not in pt and ">" not in pt)
check("去 script/style", "var x" not in pt and ".a{}" not in pt)
check("保留文本", "第一段" in pt and "加粗" in pt and "第二段" in pt)
check("HTML 实体解码", "&" in pt)
check("块级换行", "\n" in pt)

# ---- create_draft payload（mock token + post） ----
class FakeResp:
    def __init__(self, data): self._d = data
    def json(self): return self._d
    @property
    def status_code(self): return 200

captured = {}
def fake_post(url, data=None, **kw):
    import json as _json
    captured["url"] = url
    captured["params"] = kw.get("params")
    captured["data"] = _json.loads(data.decode("utf-8")) if isinstance(data, (bytes, bytearray)) else data
    return FakeResp({"media_id": "M1", "errcode": 0, "errmsg": "ok"})

with mock.patch.object(pub.requests, "get", return_value=FakeResp({"access_token": "T"})), \
     mock.patch.object(pub.requests, "post", side_effect=fake_post):
    res = pub.create_draft("T", "标题", "<p>正文</p>", "摘要")
    check("create_draft 返回 media_id", res.media_id == "M1", str(res.media_id))
    check("payload 含 title", captured["data"]["articles"][0]["title"] == "标题")
    check("payload 含 content", "正文" in captured["data"]["articles"][0]["content"])
    check("payload 含 digest", captured["data"]["articles"][0]["digest"] == "摘要")
    check("payload 含 access_token 参数", captured["params"].get("access_token") == "T")

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)