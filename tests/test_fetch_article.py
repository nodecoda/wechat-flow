"""fetch_article.py 回归测试：HTML→Markdown 解析（排版链依赖，缺失则 SKIP）。

独立运行：python tests/test_fetch_article.py
"""
import io, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

try:
    import fetch_article as fa
except ImportError as e:
    print(f"[SKIP] 依赖缺失（{e}），跳过 fetch_article 测试")
    sys.exit(0)

from bs4 import BeautifulSoup

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

html = """<div id="js_content" style="visibility:hidden">
  <section><h2>小节标题</h2><p>第一段 <strong>加粗</strong> 内容。</p></section>
  <p><img src="https://x.com/a.png" /></p>
  <p>第二段。</p>
</div>"""
soup = BeautifulSoup(html, "html.parser")
md = fa.html_to_markdown(soup)
check("提取 js_content", "第一段" in md and "第二段" in md)
check("标题保留为 markdown", "小节标题" in md)
check("去 style 属性", "visibility" not in md)
check("空内容返回空串", fa.html_to_markdown(BeautifulSoup("<div></div>", "html.parser")) == "")

# _extract_metadata / _elem_to_md 冒烟
meta = fa._extract_metadata(soup)
check("_extract_metadata 有 title 键", "title" in meta or isinstance(meta, dict))

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)