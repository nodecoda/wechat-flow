"""fetch_stats.py 回归测试：token 请求与历史回填（mock 网络 + 临时目录隔离）。

独立运行：python tests/test_fetch_stats.py
"""
import io, sys, tempfile
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import fetch_stats as fs

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

class FakeResp:
    def __init__(self, data): self._d = data
    def json(self): return self._d

# _get_access_token 成功
with mock.patch.object(fs.requests, "get", return_value=FakeResp({"access_token": "TOK"})):
    check("_get_access_token 成功", fs._get_access_token("a", "b") == "TOK")

# _get_access_token 错误 → ValueError
with mock.patch.object(fs.requests, "get", return_value=FakeResp({"errcode": 1, "errmsg": "x"})):
    try:
        fs._get_access_token("a", "b")
        check("token 错误抛 ValueError", False)
    except ValueError:
        check("token 错误抛 ValueError", True)

# fetch_article_summary 解析 list 响应
with mock.patch.object(fs.requests, "post", return_value=FakeResp({"list": [{"a": 1}]})):
    check("fetch_article_summary 解析", fs.fetch_article_summary("T", "2026-08-01") == [{"a": 1}])

# update_history：patch fs.SKILL_DIR 到临时目录，隔离真实 history.yaml
import shutil, yaml
tmp = tempfile.mkdtemp(prefix="fstats_")
old_dir = fs.SKILL_DIR
try:
    hist = Path(tmp) / "history.yaml"
    yaml.dump([{"title": "t", "date": "2026-08-01", "stats": {"read_count": 0}}],
              open(hist, "w", encoding="utf-8"), allow_unicode=True, default_flow_style=False)
    fs.SKILL_DIR = Path(tmp)
    fs.update_history([{"title": "t", "int_page_read_count": 100, "share_count": 3,
                        "old_like_count": 1, "like_count": 2, "target_user": 200}])
    data = yaml.safe_load(hist.read_text(encoding="utf-8"))
    check("update_history 命中并更新", isinstance(data, list) and data[0].get("stats", {}).get("read_count") == 100)
    check("update_history read_rate 计算", data[0]["stats"]["read_rate"] == 50.0, str(data[0]["stats"].get("read_rate")))
    check("update_history like 合并", data[0]["stats"]["like_count"] == 3)
finally:
    fs.SKILL_DIR = old_dir
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)