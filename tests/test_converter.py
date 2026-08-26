"""converter.py 回归测试：Markdown→微信 HTML 核心转换（排版链依赖，缺失则 SKIP）。

独立运行：python tests/test_converter.py
"""
import io, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "toolkit"))

try:
    from converter import WeChatConverter
except ImportError as e:
    print(f"[SKIP] 依赖缺失（{e}），跳过 converter 测试")
    sys.exit(0)

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

cv = WeChatConverter(theme=None)
md = "# 我的标题\n\n## 第一节\n\n正文 **加粗** 与 [链接](https://x.com)。\n\n- 列表项一\n- 列表项二\n"
res = cv.convert(md)
check("title 提取", res.title == "我的标题", str(res.title))
check("html 含正文", "第一节" in res.html and "正文" in res.html)
check("html 含加粗", "<strong" in res.html or "<b" in res.html)
check("html 不重复 H1", res.html.count("我的标题") <= 1)
check("digest 非空", len(res.digest) > 0)
check("images 列表", isinstance(res.images, list))

# 图片引用
md2 = "# T\n\n![图](https://x.com/i.png)\n"
res2 = cv.convert(md2)
check("images 提取", any("i.png" in i for i in res2.images), str(res2.images))

# 空输入
res3 = cv.convert("")
check("空输入 title 空", res3.title == "")

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)