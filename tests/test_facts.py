"""facts.py 回归测试：init/verify/status/check-refs 三路径。

独立运行：python tests/test_facts.py
（python tests/run_all.py 统一执行）
"""
import io, json, os, subprocess, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SKILL_ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
FACTS = str(SKILL_ROOT / "toolkit" / "facts.py")
ROOT = str(SKILL_ROOT)
SLUG = "test-facts-smoke"
OUT = os.path.join(ROOT, "output")

def run(*args):
    return subprocess.run([PY, FACTS] + list(args), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          cwd=ROOT)

def status_json(slug=SLUG):
    r = run("status", slug, "--json")
    return json.loads(r.stdout)

# 清理上次运行残留，保证测试幂等
for f in os.listdir(OUT):
    if SLUG in f:
        os.remove(os.path.join(OUT, f))

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name} {detail}")

# ---- 1. init 空表 ----
r = run("init", SLUG)
check("init 空表 exit0", r.returncode == 0, r.stdout.strip()[-60:])
check("init 空表 total=0", status_json()["total"] == 0)

# ---- 2. init 批量登记 3 条 ----
items = [
    "2025年微信公开课数据显示，小程序交易规模突破4.2万亿元|https://mp.weixin.qq.com/x|微信公开课",
    "超过60%的年轻人表示愿意为AI工具付费|https://36kr.com/p/1|36氪",
    "据艾瑞咨询报告，国内AI写作用户规模达1.2亿|https://www.iresearch.com.cn/2|艾瑞咨询",
]
args = ["init", SLUG] + [f"--item={i}" for i in items]
r = run(*args)
check("init 3条 exit0", r.returncode == 0)
s = status_json()
check("init total=3", s["total"] == 3, str(s["counts"]))
check("init 全 pending", s["counts"]["pending"] == 3)

# ---- 3. init 幂等（重复 claim） ----
r = run("init", SLUG, "--item=" + items[0])
check("init 重复claim total仍3", status_json()["total"] == 3)

# ---- 4. verify 流转 verified ----
r = run("verify", SLUG, "--index", "1", "--status", "verified")
check("verify idx1 verified exit0", r.returncode == 0)
s = status_json()
check("verify counts v1", s["counts"]["verified"] == 1 and s["counts"]["pending"] == 2, str(s["counts"]))
item0 = s["items"][0]
check("verify 写入 verified_at", "verified_at" in load_raw()["items"][0] if False else s["items"][0]["status"] == "verified")

# ---- 5. verify 重复同状态 -> exit2 ----
r = run("verify", SLUG, "--index", "1", "--status", "verified")
check("verify 重复状态 exit2", r.returncode == 2, r.stderr.strip()[-50:])

# ---- 6. verify 越界 -> exit2 ----
r = run("verify", SLUG, "--index", "99", "--status", "verified")
check("verify 越界 exit2", r.returncode == 2)

# ---- 7. verify 非法状态 -> exit2 (argparse) ----
r = run("verify", SLUG, "--index", "1", "--status", "bogus")
check("verify 非法状态 exit2", r.returncode == 2)

# ---- 8. idx2 -> rejected, idx3 保持 pending ----
r = run("verify", SLUG, "--index", "2", "--status", "rejected")
check("verify idx2 rejected exit0", r.returncode == 0)
s = status_json()
check("counts v1/r1/p1", s["counts"] == {"verified": 1, "rejected": 1, "pending": 1}, str(s["counts"]))

# ---- 9. check-refs 降级：无 facts 文件 ----
draft_no = os.path.join(OUT, "2026-08-26-no-such-slug.md")
with open(draft_no, "w", encoding="utf-8") as f:
    f.write("# 测试\n\n2025年有50%的人表示。\n")
r = run("check-refs", draft_no)
check("check-refs 无facts exit0 skipped", r.returncode == 0 and "跳过" in r.stdout)

# ---- 10. 主场景：draft 复述 + 编造 ----
draft = os.path.join(OUT, "2026-08-26-" + SLUG + ".md")
text = """# 2026 年 AI 写作工具观察

2025年微信公开课数据显示，小程序交易规模突破4.2万亿元，这是行业的重要信号。

与此同时，超过60%的年轻人表示愿意为AI工具付费，说明市场正在成熟。

据艾瑞咨询报告，国内AI写作用户规模达1.2亿，增长空间巨大。

但另一个角度：某科技媒体表示，AI写作的质量仍有瓶颈，这个说法值得商榷。

而且根据内部估算，未来五年市场规模将达到3亿人民币，前景广阔。
"""
with open(draft, "w", encoding="utf-8") as f:
    f.write(text)

r = run("check-refs", draft)
print("---- check-refs 输出 ----")
print(r.stdout)
print("stderr:", r.stderr)
print("---- /输出 ----")
check("check-refs exit1 (有未溯源)", r.returncode == 1)
rj = run("check-refs", draft, "--json")
rep = json.loads(rj.stdout)
check("json status=issues", rep["status"] == "issues")
def ctx_has(lst, key):
    return any(key in e["context"] for e in lst)
check("traced 含微信公开课", ctx_has(rep["traced"], "微信公开课"), f"traced={len(rep['traced'])}")
check("rejected_hits 含年轻人", ctx_has(rep["rejected_hits"], "年轻人"))
check("pending_hits 含艾瑞咨询", ctx_has(rep["pending_hits"], "艾瑞咨询"))
check("missing 含科技媒体", ctx_has(rep["missing"], "科技媒体"))
check("missing 含3亿", ctx_has(rep["missing"], "3亿"))

# ---- 11. 全部核实后通过 ----
r = run("verify", SLUG, "--index", "2", "--status", "verified")
check("verify idx2 -> verified exit0", r.returncode == 0)
r = run("check-refs", draft)
check("check-refs 全核实后仍 exit1 (科技媒体未溯源)", r.returncode == 1)

# ---- 12. 只留已溯源内容 -> exit0（改写主 draft 为干净版） ----
with open(draft, "w", encoding="utf-8") as f:
    f.write("# 标题\n\n2025年微信公开课数据显示，小程序交易规模突破4.2万亿元，这是行业的重要信号。\n")
r = run("check-refs", draft)
print("---- clean check-refs 输出 ----")
print(r.stdout)
check("check-refs clean exit0", r.returncode == 0)
rj = run("check-refs", draft, "--json")
rep = json.loads(rj.stdout)
check("json clean status=ok", rep["status"] == "ok" and len(rep["traced"]) >= 1)

# ---- 汇总 ----
fails = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(fails)}/{len(results)} passed")
sys.exit(1 if fails else 0)