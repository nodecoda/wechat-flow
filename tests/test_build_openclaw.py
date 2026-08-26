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
name: wewrite
description: 测试
allowed-tools:
  - Bash
  - Read
  - Write
---
"""
out = bo.transform_frontmatter(fm)
check("allowed-tools 键被剥离", "allowed-tools" not in out)
check("name 保留", "name: wewrite" in out)
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

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)