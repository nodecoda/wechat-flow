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

# ---- 学习回路：save_lesson / aggregate_patterns / compute_confidence ----
import tempfile, shutil, yaml as _yaml

tmp = tempfile.mkdtemp(prefix="led_")
old_dir = le.SKILL_DIR
try:
    le.SKILL_DIR = Path(tmp)
    diff = le.compute_diff("# 原\n\n## A\n\n旧段落\n", "# 新\n\n## A\n\n新段落\n")
    f1 = le.save_lesson(diff, "draft.md", "final.md")
    check("save_lesson 生成 lessons 文件", f1.exists() and "lessons" in str(f1))
    data1 = _yaml.safe_load(f1.read_text(encoding="utf-8"))
    check("save_lesson 含 diff_summary", "diff_summary" in data1)
    check("save_lesson 含 patterns", isinstance(data1.get("patterns", []), list))

    # 同日期第二篇 → 文件名递增
    f2 = le.save_lesson(diff, "d2.md", "f2.md")
    check("save_lesson 同名递增", f2.name != f1.name)

    # aggregate_patterns：合并同 key 出现次数
    lessons = [
        {"date": "2026-08-01", "timestamp": "2026-08-01T10:00:00",
         "patterns": [{"key": "word_sub", "type": "word_sub", "description": "d", "rule": "r"}]},
        {"date": "2026-08-02", "timestamp": "2026-08-02T10:00:00",
         "patterns": [{"key": "word_sub", "type": "word_sub", "description": "d", "rule": "r"}]},
    ]
    agg = le.aggregate_patterns(lessons)
    check("aggregate_patterns 合并", len(agg) == 1 and agg[0]["occurrences"] == 2, str(agg))
    check("aggregate_patterns 排序字段", "key" in agg[0] and "confidence" in agg[0])

    # compute_confidence
    check("confidence 1次", le.compute_confidence(1, "2026-08-25T00:00:00", "2026-08-25T00:00:00") == 5.0, str(le.compute_confidence(1, "2026-08-25T00:00:00", "2026-08-25T00:00:00")))
    check("confidence 3次", le.compute_confidence(3, "2026-08-25T00:00:00", "2026-08-25T00:00:00") == 9.0, str(le.compute_confidence(3, "2026-08-25T00:00:00", "2026-08-25T00:00:00")))
    check("confidence 旧时间衰减", le.compute_confidence(3, "2026-01-01T00:00:00", "2026-01-01T00:00:00") <= 6.0, str(le.compute_confidence(3, "2026-01-01T00:00:00", "2026-01-01T00:00:00")))
finally:
    le.SKILL_DIR = old_dir
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)