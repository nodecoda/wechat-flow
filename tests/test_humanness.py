"""humanness_score.py 回归测试：禁用词方向语义反例（0 禁词必须优于 1 禁词）。

实战发现：banned_words 曾被钟形校准惩罚，出现"0 禁词比 1 禁词更像 AI"的倒置。
本测试锁定修复：banned_words 是硬规则，不参与钟形校准。

独立运行：python tests/test_humanness.py
"""
import io, json, os, subprocess, sys, tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
H = str(SKILL_ROOT / "scripts" / "humanness_score.py")

def score(text):
    d = tempfile.mkdtemp(prefix="bell_")
    try:
        p = os.path.join(d, "t.md")
        open(p, "w", encoding="utf-8").write(text)
        r = subprocess.run([PY, H, p, "--json"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return json.loads(r.stdout)["composite_score"]
    finally:
        import shutil; shutil.rmtree(d, ignore_errors=True)

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

base = "# 标题\n\n今天天气不错，我们去爬山。风景很好，心情舒畅。\n\n回来的路上买了水果，苹果很甜。\n"
s0 = score(base)
s1 = score(base.replace("不错", "不错，综上所述"))
check("0 禁词优于 1 禁词（方向语义）", s0 <= s1, f"0-banned={s0} 1-banned={s1}")

fails = [n for n, ok in results if not ok]
print(f"\n{len(results)-len(fails)}/{len(results)} passed")
sys.exit(1 if fails else 0)
