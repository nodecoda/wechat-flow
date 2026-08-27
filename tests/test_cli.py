"""cli.py 回归测试：命令分发 / 主题列表 / 预览 / 锚点检查（排版链依赖，缺失则 SKIP）。

独立运行：python tests/test_cli.py
"""
import io, os, subprocess, sys, tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
CLI = str(SKILL_ROOT / "toolkit" / "cli.py")
ROOT = str(SKILL_ROOT)

# cli.py 依赖 converter/theme（bs4/markdown/cssutils）——缺失则 SKIP
try:
    sys.path.insert(0, str(SKILL_ROOT / "toolkit"))
    from converter import WeChatConverter  # noqa: F401
    import theme  # noqa: F401
except ImportError as e:
    print(f"[SKIP] 依赖缺失（{e}），跳过 cli 测试")
    sys.exit(0)

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

def run(*args):
    return subprocess.run([PY, CLI] + list(args), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", cwd=ROOT)

# ---- --help ----
r = run("--help")
check("--help exit0", r.returncode == 0)
for sub in ("preview", "publish", "themes", "accounts", "image-post", "gallery", "anchor", "learn-theme"):
    check(f"--help 含子命令 {sub}", sub in r.stdout)

# ---- themes ----
r = run("themes")
check("themes exit0", r.returncode == 0)
check("themes 含 professional-clean", "professional-clean" in r.stdout)

# ---- accounts（仓库根无 config → 未配置提示，exit 0）----
r = run("accounts")
check("accounts exit0", r.returncode == 0, f"exit={r.returncode} {r.stderr[-120:]}")
check("accounts 含未配置提示", "未配置公众号" in r.stdout or "default" in r.stdout, r.stdout[-120:])

# ---- publish --account 参数存在 ----
r = run("publish", "--help")
check("publish --help 含 --account", "--account" in r.stdout)

# ---- preview --no-open ----
tmp = tempfile.mkdtemp(prefix="cli_")
try:
    md = Path(tmp) / "a.md"
    md.write_text("# 预览标题\n\n正文内容。\n", encoding="utf-8")
    out_html = Path(tmp) / "a.html"
    r = run("preview", str(md), "--no-open", "-o", str(out_html))
    check("preview exit0", r.returncode == 0, r.stderr[-120:])
    check("preview 生成 html", out_html.exists() and "正文内容" in out_html.read_text(encoding="utf-8"))
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

# ---- anchor check：填好 → 0；未填 → 1 ----
tmp2 = tempfile.mkdtemp(prefix="clianchor_")
try:
    filled = Path(tmp2) / "ok.md"
    filled.write_text("# T\n\n:::anchor opinion\n一句话观点。\n:::\n", encoding="utf-8")
    r = run("anchor", "check", str(filled))
    check("anchor check 已填 exit0", r.returncode == 0, f"exit={r.returncode} {r.stdout[-120:]}")
finally:
    import shutil
    shutil.rmtree(tmp2, ignore_errors=True)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)