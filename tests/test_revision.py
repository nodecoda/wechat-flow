"""revision.py 回归测试：analyze / 实体命名一致性 / recheck / rollback。

独立运行：python tests/test_revision.py
"""
import io, os, subprocess, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
REV = str(SKILL_ROOT / "toolkit" / "revision.py")
ROOT = str(SKILL_ROOT)
OUT = os.path.join(ROOT, "output")

def run(*args):
    return subprocess.run([PY, REV] + list(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=ROOT)

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

# 清理残留
for f in os.listdir(OUT):
    if "test-rev" in f:
        os.remove(os.path.join(OUT, f))

# 1. analyze 带日期前缀 md → 实体命名必须为 slug（无日期前缀）
md = os.path.join(OUT, "2026-08-26-test-rev.md")
open(md, "w", encoding="utf-8").write("# 测试文章\n\n第一段内容，讲一个道理。\n\n第二段内容，补充一个观点。\n")
r = run("analyze", md)
check("analyze exit0", r.returncode == 0)
check("实体命名无日期前缀", os.path.exists(os.path.join(OUT, "test-rev-revision.yaml")),
      "expected test-rev-revision.yaml")
check("不产生日期前缀实体", not os.path.exists(os.path.join(OUT, "2026-08-26-test-rev-revision.yaml")))

# 2. 报告含 layers 且含 param 层键
import yaml
rep = yaml.safe_load(open(os.path.join(OUT, "test-rev-revision.yaml"), encoding="utf-8"))
check("报告含五层键", set(rep["layers"].keys()) == {"structure", "paragraph", "sentence", "wording", "param"},
      str(rep["layers"].keys()))
check("baseline humanness 数值", isinstance(rep["baseline"].get("humanness"), (int, float)))

# 3. recheck
r = run("recheck", md)
check("recheck exit0", r.returncode == 0 and "复检" in r.stdout)

# 4. rollback 无备份 → 提示
r = run("rollback", md)
check("rollback 无备份提示", r.returncode == 0 and ("备份" in r.stdout or "回滚" in r.stdout))

# 清理
for f in os.listdir(OUT):
    if "test-rev" in f:
        os.remove(os.path.join(OUT, f))

fails = [n for n, ok in results if not ok]
print(f"\n{len(results)-len(fails)}/{len(results)} passed")
sys.exit(1 if fails else 0)
