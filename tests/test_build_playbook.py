"""build_playbook.py 回归测试：语料加载与统计、批次切分。

独立运行：python tests/test_build_playbook.py
"""
import io, sys, tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import build_playbook as bp

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

# ---- load_corpus（monkeypatch SKILL_DIR 到临时目录） ----
tmp = tempfile.mkdtemp(prefix="bp_")
try:
    corpus = Path(tmp) / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text("# 第一篇\n\n## 小节一\n\n正文段落一。\n\n## 小节二\n\n正文段落二。\n", encoding="utf-8")
    (corpus / "b.md").write_text("# 第二篇\n\n只有一段。\n", encoding="utf-8")
    (corpus / "empty.md").write_text("   \n\n", encoding="utf-8")  # 空白，应跳过

    old_dir = bp.SKILL_DIR
    bp.SKILL_DIR = Path(tmp)
    try:
        arts = bp.load_corpus()
    finally:
        bp.SKILL_DIR = old_dir

    check("load_corpus 跳过空白文件", len(arts) == 2, f"n={len(arts)}")
    check("标题提取", {a["title"] for a in arts} == {"第一篇", "第二篇"})
    a = next(x for x in arts if x["filename"] == "a.md")
    # 实现按空行(\n\n)切分计数，标题行也算块：预期 5
    check("段落数", a["paragraph_count"] == 5, str(a["paragraph_count"]))
    check("h2 数", a["h2_count"] == 2, str(a["h2_count"]))

    # ---- compute_corpus_stats ----
    stats = bp.compute_corpus_stats(arts)
    check("stats total_articles=2", stats["total_articles"] == 2)
    check("stats avg_title_length", stats["avg_title_length"] > 0)
    check("stats title_length_range", "-" in stats["title_length_range"])
    check("空语料返回 {} ", bp.compute_corpus_stats([]) == {})

    # ---- build_analysis_batches ----
    batches = bp.build_analysis_batches(list(range(7)), 3)
    check("批次切分 7/3 → 3 批", len(batches) == 3, str([len(b) for b in batches]))
    check("批内数量 [3,3,1]", [len(b) for b in batches] == [3, 3, 1])
    check("空批次", bp.build_analysis_batches([], 5) == [])
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)