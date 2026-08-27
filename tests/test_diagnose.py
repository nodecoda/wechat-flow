"""diagnose.py 回归测试：检查结果结构与汇总逻辑。

独立运行：python tests/test_diagnose.py
"""
import io, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import diagnose as dg

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

# ---- make_check ----
c = dg.make_check("config", "config_file", "pass", detail="found", impact=None)
check("make_check 结构", c == {"group": "config", "name": "config_file", "status": "pass", "detail": "found"})
c2 = dg.make_check("config", "wechat", "warn", impact="skip_publish")
check("make_check 带 impact", c2["impact"] == "skip_publish" and "detail" not in c2)

# ---- compute_summary ----
checks = [
    dg.make_check("deps", "python_packages", "pass"),
    dg.make_check("style", "style_file", "fail"),
    dg.make_check("config", "wechat_credentials", "warn", impact="skip_publish"),
    dg.make_check("dimensions", "dimension_variance", "skip"),
]
s, _recs = dg.compute_summary(checks)  # 返回 (summary, recommendations)
check("summary 计数 pass=1", s["passed"] == 1, str(s["passed"]))
check("summary 计数 warn=1", s["warnings"] == 1)
check("summary 计数 fail=1", s["failures"] == 1)
check("summary 计数 skip=1", s["skipped"] == 1)
check("summary anti_ai_score=0", s["anti_ai_score"] == 0)
check("summary 有推荐项", isinstance(_recs, list))

# 权重打满 → HIGH
high_checks = [dg.make_check("x", "style_file", "pass")]
# style_file weight=3；MAX_ANTI_AI_SCORE 需运行时读取
mx = getattr(dg, "MAX_ANTI_AI_SCORE", None)
check("MAX_ANTI_AI_SCORE 存在", mx is not None and mx > 0)
if mx:
    full = [dg.make_check("x", k, "pass") for k in dg.WEIGHTS if dg.WEIGHTS[k] > 0]
    s2, _ = dg.compute_summary(full)
    check("全绿 → anti_ai_level=HIGH", s2["anti_ai_level"] == "HIGH", s2["anti_ai_level"])

# ---- check_config：多账号配置 → pass + wechat_accounts 信息项 ----
import tempfile, os
tmp2 = tempfile.mkdtemp(prefix="diag_acc_")
old_cwd = os.getcwd()
try:
    os.chdir(tmp2)
    Path(tmp2, "config.yaml").write_text(
        "wechat:\n  default: main\n  accounts:\n"
        "    - name: main\n      appid: wx123\n      secret: s1\n"
        "    - name: sub\n      appid: wx456\n      secret: s2\n",
        encoding="utf-8",
    )
    acc_checks = dg.check_config()
    cw = next((c for c in acc_checks if c["name"] == "wechat_credentials"), None)
    check("多账号 → wechat_credentials pass", cw is not None and cw["status"] == "pass", str(cw))
    ca = next((c for c in acc_checks if c["name"] == "wechat_accounts"), None)
    check("多账号 → wechat_accounts 信息项", ca is not None and ca["status"] == "pass", str(ca))
finally:
    os.chdir(old_cwd)
    import shutil
    shutil.rmtree(tmp2, ignore_errors=True)

# ---- run_all_checks 在空仓库目录 ----
import tempfile, os
tmp = tempfile.mkdtemp(prefix="diag_")
try:
    os.chdir(tmp)
    try:
        allc = dg.run_all_checks()
        check("run_all_checks 返回列表", isinstance(allc, list) and len(allc) > 0)
        check("run_all_checks 有依赖检查", any(x["name"] == "python_packages" for x in allc))
        check("run_all_checks 有 style 检查", any(x["name"] == "style_file" for x in allc))
    finally:
        os.chdir(SKILL_ROOT)
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)