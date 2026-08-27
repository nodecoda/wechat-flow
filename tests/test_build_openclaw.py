"""build_openclaw.py 回归测试：frontmatter 剥离与 body 转换。

独立运行：python tests/test_build_openclaw.py
"""
import io, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import build_openclaw as bo

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

# ---- transform_frontmatter ----
fm = """---
name: ncoda
description: 测试
allowed-tools:
  - Bash
  - Read
  - Write
---
"""
out = bo.transform_frontmatter(fm)
check("allowed-tools 键被剥离", "allowed-tools" not in out)
check("name 保留", "name: ncoda" in out)
check("description 保留", "description: 测试" in out)
check("列表项被剥离", "- Bash" not in out)

fm2 = "---\nname: x\nallowed-tools:\n  - A\n  - B\n---\n# 正文\n"
out2 = bo.transform_frontmatter(fm2)
check("块后正文保留", "# 正文" in out2)

# ---- transform_body ----
body = "{skill_dir}/scripts/x.py 与 WebSearch 工具。\nWebSearch: 搜索\n`WebSearch` 不变"
out3 = bo.transform_body(body)
check("{skill_dir}→{baseDir}", "{baseDir}" in out3 and "{skill_dir}" not in out3)
check("WebSearch: → web_search:", "web_search:" in out3 and "WebSearch:" not in out3)
check("反引号内 WebSearch 不变", "`WebSearch`" in out3)

# ---- split_frontmatter ----
full = fm + "# 标题\n正文"
parts = bo.split_frontmatter(full)
check("split_frontmatter 返回 (frontmatter, body)", len(parts) == 2)
check("split frontmatter 含 YAML 头", "allowed-tools" in parts[0])
check("split body 保留正文", "# 标题" in parts[1])

# ---- build() e2e：临时输出目录 ----
import tempfile, shutil
tmp = tempfile.mkdtemp(prefix="bo_")
try:
    out_dir = Path(tmp) / "openclaw"
    bo.build(out_dir)
    check("build 生成 SKILL.md", (out_dir / "SKILL.md").exists())
    check("build 生成 ncoda_common.py", (out_dir / "ncoda_common.py").exists())
    check("build 生成 toolkit/facts.py", (out_dir / "toolkit" / "facts.py").exists())
    check("build 生成 scripts/humanness_score.py", (out_dir / "scripts" / "humanness_score.py").exists())
    sk = (out_dir / "SKILL.md").read_text(encoding="utf-8")
    check("build 转换 allowed-tools 剥离", "allowed-tools" not in sk)
    check("build 转换 {baseDir}", "{baseDir}" in sk)
    check("build 复制 requirements-min", (out_dir / "requirements-min.txt").exists())
    wc = (out_dir / "ncoda_common.py").read_text(encoding="utf-8")
    check("build 复制新版 ncoda_common", "ensure_skill_root" in wc)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)