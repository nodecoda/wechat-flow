"""intent.py 回归测试：scaffold / validate（三问机器可判）/ titles / lock / 降级。

独立运行：python tests/test_intent.py
"""
import io, json, os, subprocess, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
INTENT = str(SKILL_ROOT / "toolkit" / "intent.py")
ROOT = str(SKILL_ROOT)
SLUG = "test-intent"
CARD = os.path.join(ROOT, "output", f"{SLUG}-intent.yaml")

def run(*args):
    return subprocess.run([PY, INTENT] + list(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=ROOT)

# 清理残留
for f in os.listdir(os.path.join(ROOT, "output")):
    if SLUG in f:
        os.remove(os.path.join(ROOT, "output", f))

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

# 1. scaffold
r = run("scaffold", SLUG, "--topic", "测试选题")
check("scaffold exit0", r.returncode == 0)
check("intent.yaml 生成", os.path.exists(CARD))

# 2. 填充 → validate 通过
import yaml
card = yaml.safe_load(open(CARD, encoding="utf-8"))
card["thesis"] = "选题是测试，但判断要有信息差——从A到B的认知变化值得一说"
card["info_gap"] = {"from": "读者以为A", "to": "读完知道B"}
card["boundary"] = "仅适用于测试场景，不适用于生产"
card["evidence"] = [{"claim": "测试证据", "source": "测试来源", "url": "https://example.com"}]
card["thesis_candidates"] = ["候选一", "候选二", "候选三"]
open(CARD, "w", encoding="utf-8").write(yaml.dump(card, allow_unicode=True, default_flow_style=False))

r = run("validate", CARD)
check("validate 三问通过", r.returncode == 0 and "通过" in r.stdout)

# 3. validate 缺信息差 → 不过（回归：info_gap 缺失应 fail）
card2 = yaml.safe_load(open(CARD, encoding="utf-8"))
card2["info_gap"] = {"from": "", "to": ""}
open(CARD, "w", encoding="utf-8").write(yaml.dump(card2, allow_unicode=True, default_flow_style=False))
r = run("validate", CARD)
check("validate 缺信息差 fail", r.returncode == 1 and "信息差" in r.stdout)
card["info_gap"] = {"from": "读者以为A", "to": "读完知道B"}
open(CARD, "w", encoding="utf-8").write(yaml.dump(card, allow_unicode=True, default_flow_style=False))

# 4. titles
r = run("titles", CARD)
check("titles 生成候选", r.returncode == 0 and "标题候选" in r.stdout)

# 5. lock 状态流转
r = run("lock", CARD)
card = yaml.safe_load(open(CARD, encoding="utf-8"))
check("lock 状态 = locked", r.returncode == 0 and card.get("status") == "locked")

# 6. 降级：缺文件 → exit2
r = run("validate", os.path.join(ROOT, "output", "test-nonexistent-intent.yaml"))
check("validate 缺文件 exit2", r.returncode == 2)

# 清理
for f in os.listdir(os.path.join(ROOT, "output")):
    if SLUG in f:
        os.remove(os.path.join(ROOT, "output", f))

fails = [n for n, ok in results if not ok]
print(f"\n{len(results)-len(fails)}/{len(results)} passed")
sys.exit(1 if fails else 0)
