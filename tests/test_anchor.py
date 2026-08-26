# anchor.py 回归：generate 占位判未填写；用户替换后判已填写；无锚点 exit0
import io, os, subprocess, sys, tempfile
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
ANCHOR = str(SKILL_ROOT / "toolkit" / "anchor.py")
d = tempfile.mkdtemp(prefix="anchor_test_")
md = os.path.join(d, "test.md")
open(md, "w", encoding="utf-8").write("# 标题\n\n第一段内容。\n\n第二段内容。\n")
r = subprocess.run([PY, ANCHOR, "generate", md, "--count", "2"], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("generate rc:", r.returncode, r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[:100])
r = subprocess.run([PY, ANCHOR, "check", md], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("check(unfilled) rc:", r.returncode, "|", [l for l in r.stdout.splitlines() if "total" in l or "所有" in l])
# 用户填写第一个锚点
t = open(md, encoding="utf-8").read()
t = t.replace("在这里加一句你自己的话：写一段真实的个人经历或感受（1-2 句即可）。", "我去年夏天自己开车跑了趟川西，那段路我永远忘不了。", 1)
open(md, "w", encoding="utf-8").write(t)
r = subprocess.run([PY, ANCHOR, "check", md], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("check(1 filled) rc:", r.returncode, "|", [l for l in r.stdout.splitlines() if "编辑锚点" in l])
assert r.returncode == 1
print("PASS: placeholder->unfilled, filled->filled")
os.unlink(md); os.rmdir(d)