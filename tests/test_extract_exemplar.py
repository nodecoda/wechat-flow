"""extract_exemplar.py 回归测试：分类检测与段提取纯逻辑。

独立运行：python tests/test_extract_exemplar.py
"""
import io, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import extract_exemplar as ee

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

# ---- extract_headings ----
check("extract_headings H2", ee.extract_headings("# T\n## 甲\n## 乙\n") == ["甲", "乙"])
check("extract_headings 忽略 H1/H3", ee.extract_headings("# T\n### 丙\n") == [])

# ---- extract_opening ----
paras = ["开篇一句。", "第二段内容比较长一些。", "第三段。"]
op = ee.extract_opening(paras, max_chars=10)
check("extract_opening 按 max_chars 截断", "开篇一句。" in op and "第二段" not in op)
op2 = ee.extract_opening(paras, max_chars=100)
check("extract_opening 全取", "第三段。" in op2)

# ---- count_short_paragraphs ----
text = "# 标题\n\n好。\n\n这是一段完整的正文内容。\n\n嗯。\n"
check("count_short_paragraphs=2", ee.count_short_paragraphs(text) == 2)

# ---- detect_category ----
# 数据密集 → tech-opinion
tech = "据艾瑞报告，市场规模达 1.2 亿元，用户增长 60%。" * 5
check("detect_category 数据密集→tech-opinion", ee.detect_category(tech, [tech], []) == "tech-opinion")
# 故事标记 → story-emotional
story = "我那天记得第一次见到她，后来我们都笑了。" * 8
check("detect_category 故事→story-emotional", ee.detect_category(story, [story], []) == "story-emotional")
# ≥5 个 H2 → list-practical
h2s = [f"## 第{i}点" for i in range(6)]
check("detect_category 多H2→list-practical", ee.detect_category("普通文本", ["普通文本"], h2s) == "list-practical")

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)