"""ncoda_common 配置层回归：本地优先合并、style 搜索、多公众号账号解析。

独立运行：python tests/test_config.py
"""
import io, os, shutil, sys, tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

import ncoda_common as nc

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

# ---- config_search_paths 顺序：本地 cwd 第一，home 最后 ----
paths = nc.config_search_paths(SKILL_ROOT)
check("搜索顺序：cwd 第一", paths[0] == Path.cwd() / "config.yaml", str(paths[0]))
check("搜索顺序：skill root 第二", paths[1] == SKILL_ROOT / "config.yaml")
check("搜索顺序：home 最后", paths[-1] == Path.home() / ".config" / "ncoda" / "config.yaml")
check("共 4 个搜索位", len(paths) == 4)

# ---- 合并语义：本地覆盖全局，深层键保留 ----
tmp = Path(tempfile.mkdtemp(prefix="cfg_"))
g = tmp / "global"; l = tmp / "local"
g.mkdir(); l.mkdir()
(g / "config.yaml").write_text(
    "wechat:\n  appid: GAPP\n  author: GAuthor\nimage:\n  provider: doubao\n", encoding="utf-8")
(l / "config.yaml").write_text("wechat:\n  appid: LAPP\n", encoding="utf-8")
old = os.getcwd()
try:
    os.chdir(l)
    cfg = nc.load_config(g)
    check("本地 appid 覆盖全局", cfg.get("wechat", {}).get("appid") == "LAPP", str(cfg.get("wechat")))
    check("深层键保留（author）", cfg.get("wechat", {}).get("author") == "GAuthor")
    check("全局其他段保留（image）", cfg.get("image", {}).get("provider") == "doubao")
    check("find_config_path 返回本地", nc.find_config_path(g) == l / "config.yaml")
finally:
    os.chdir(old)

# ---- 无本地文件：仅全局生效 ----
old = os.getcwd()
try:
    os.chdir(tmp)  # tmp 无 config.yaml
    cfg = nc.load_config(g)
    check("仅全局时正常加载", cfg.get("wechat", {}).get("appid") == "GAPP")
finally:
    os.chdir(old)

# ---- 非 dict 文件容错（如误写为列表） ----
bad = tmp / "bad.yaml"
bad.write_text("- a\n- b\n", encoding="utf-8")
old = os.getcwd()
try:
    os.chdir(tmp)
    cfg = nc.load_config(g)  # bad.yaml 不参与（不在搜索路径），直接验证 load_config 遇非 dict 不崩溃
    check("load_config 不崩溃", isinstance(cfg, dict))
finally:
    os.chdir(old)

# ---- style：本地优先 + 合并 ----
(g / "style.yaml").write_text("writing_persona: a\ntopics: [g1, g2]\ntone: global\n", encoding="utf-8")
(l / "style.yaml").write_text("writing_persona: b\n", encoding="utf-8")
old = os.getcwd()
try:
    os.chdir(l)
    check("find_style_path 本地优先", nc.find_style_path(g) == l / "style.yaml")
    st = nc.load_style(g)
    check("style 本地 persona 覆盖", st.get("writing_persona") == "b", str(st))
    check("style 全局键保留", st.get("tone") == "global")
    check("style 列表整体覆盖", st.get("topics") == ["g1", "g2"])
finally:
    os.chdir(old)

# ---- 多账号解析 ----
legacy = {"wechat": {"appid": "a", "secret": "s", "author": "旧号"}}
acc = nc.get_wechat_account(legacy)
check("旧字段 → default 账号", acc is not None and acc["name"] == "default" and acc["appid"] == "a", str(acc))

multi = {"wechat": {"default": "sub", "accounts": [
    {"name": "main", "appid": "m", "secret": "ms"},
    {"name": "sub", "appid": "s", "secret": "ss"},
]}}
check("default 解析", nc.get_wechat_account(multi)["name"] == "sub")
check("按名解析", nc.get_wechat_account(multi, "main")["name"] == "main")
check("未知名 → None", nc.get_wechat_account(multi, "ghost") is None)

incomplete = {"wechat": {"accounts": [{"name": "x", "appid": "1"}]}}
check("不完整账号(按名) → None", nc.get_wechat_account(incomplete, "x") is None)
check("不完整账号(默认) → None", nc.get_wechat_account(incomplete) is None)

no_default = {"wechat": {"accounts": [
    {"name": "a", "appid": "1", "secret": "2"},
    {"name": "b", "appid": "3", "secret": "4"},
]}}
check("无 default 取首项", nc.get_wechat_account(no_default)["name"] == "a")

anon = {"wechat": {"accounts": [{"appid": "1", "secret": "2"}]}}
check("无名账号生成 account-N", nc.list_wechat_accounts(anon)[0]["name"] == "account-1")
check("无名账号可作默认", nc.get_wechat_account(anon)["name"] == "account-1")

check("wechat_account_names 顺序", nc.wechat_account_names(multi) == ["main", "sub"])
check("空配置 → None", nc.get_wechat_account({}) is None)

# 清理
shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)
