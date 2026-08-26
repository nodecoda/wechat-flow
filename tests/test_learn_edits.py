"""learn_edits.py 回归测试：markdown 清洗、diff 结构化、标题提取。

独立运行：python tests/test_learn_edits.py
"""
import io, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import learn_edits as le

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

# ---- markdown_to_plaintext ----
md = "# 标题\n\n这是**加粗**和*斜体*，还有 `代码` 与 [链接](https://x.com)。\n<!-- 编辑锚点 -->\n\n<img src=x>图片\n"
pt = le.markdown_to_plaintext(md)
check("去标题标记", "# 标题" not in pt and "标题" in pt)
check("去粗体标记", "**" not in pt and "加粗" in pt)
check("去注释", "编辑锚点" not in pt)
check("链接→文本", "[链接]" not in pt and "链接" in pt)

# ---- extract_title ----
check("extract_title H1", le.extract_title("# 我的标题\n正文") == "我的标题")
check("extract_title 忽略 H2", le.extract_title("## 小节\n正文") == "")
check("extract_title 空", le.extract_title("无标题正文") == "")

# ---- compute_diff ----
draft = "# 原标题\n\n## 第一节\n\n旧内容。\n\n新增前的段落。\n"
final = "# 新标题\n\n## 第一节\n\n旧内容。\n\n## 第二节\n\n新段落。\n"
d = le.compute_diff(draft, final)
check("title_changed=True", d["title_changed"] is True)
check("structure_changed=True", d["structure_changed"] is True)
check("final_h2s 含第二节", any("第二节" in h for h in d["final_h2s"]), str(d["final_h2s"]))
check("lines_added>0", d["lines_added"] > 0, str(d["lines_added"]))
check("char_diff>0", d["char_diff"] > 0, str(d["char_diff"]))

same = le.compute_diff(draft, draft)
check("无改动 title_changed=False", same["title_changed"] is False)
check("无改动 structure_changed=False", same["structure_changed"] is False)
check("无改动 lines_added=0", same["lines_added"] == 0)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)