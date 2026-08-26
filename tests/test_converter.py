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

# ---- 容器语法（:::dialogue / :::callout / :::timeline / :::quote / :::anchor） ----
md_c = """# T

:::callout tip
这是一个提示。
:::

:::dialogue
左气泡
> 右气泡
:::

:::timeline
**阶段一** 描述一
阶段二 描述二
:::

:::quote
金句内容
:::

:::anchor opinion
在这里写下你的观点。
:::
"""
res_c = cv.convert(md_c)
check("callout 渲染", "提示" in res_c.html and "TIP" in res_c.html)
check("dialogue 渲染左右气泡", "左气泡" in res_c.html and "右气泡" in res_c.html)
check("timeline 渲染", "阶段一" in res_c.html and "描述二" in res_c.html)
check("quote 渲染", "金句内容" in res_c.html)
check("anchor 渲染 data-anchor", 'data-anchor="opinion"' in res_c.html)

# ---- digest ≤ 120 字节 ----
md_d = "# T\n\n" + "这是用于生成摘要的正文内容。" * 40
res_d = cv.convert(md_d)
digest = getattr(res_d, "digest", "")
check("digest 非空", len(digest) > 0)
check("digest ≤120 字节", len(digest.encode("utf-8")) <= 120, f"{len(digest.encode('utf-8'))}B")
check("digest 排除 anchor 块", "data-anchor" not in digest)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)