"""learn_theme.py 回归测试：颜色工具纯逻辑（排版链依赖，缺失则 SKIP）。

独立运行：python tests/test_learn_theme.py
"""
import io, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

try:
    import learn_theme as lt
except ImportError as e:
    print(f"[SKIP] 依赖缺失（{e}），跳过 learn_theme 测试")
    sys.exit(0)

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

check("rgb() 转换", lt.rgb_to_hex("rgb(255, 0, 0)") == "#ff0000")
check("rgba() 转换", lt.rgb_to_hex("rgba(0, 128, 255, 0.5)") == "#0080ff")
check("hex 透传小写", lt.rgb_to_hex("#FF00AA") == "#ff00aa")
check("空格容错", lt.rgb_to_hex("rgb( 10 , 20 , 30 )") == "#0a141e")
check("非字符串透传", lt.rgb_to_hex(123) == 123)
check("无匹配原样返回", lt.rgb_to_hex("linear-gradient(1,2)") == "linear-gradient(1,2)")

# ---- 颜色亮度 / 灰阶 / 调整 ----
check("lightness 白=1.0", lt.lightness("#ffffff") == 1.0)
check("lightness 黑=0.0", lt.lightness("#000000") == 0.0)
check("lightness 非法→0.5", lt.lightness("notacolor") == 0.5)
check("is_gray 灰", lt.is_gray("#808080") is True)
check("is_gray 彩色", lt.is_gray("#ff0000") is False)
check("adjust_lightness 目标亮度", lt.adjust_lightness("#000000", 1.0) == "#ffffff")
check("adjust_lightness 非法原样", lt.adjust_lightness("x", 0.5) == "x")
check("_parse_px", lt._parse_px("16px") == 16.0)
check("_parse_px 无单位", lt._parse_px("16") is None)
check("_parse_px 空", lt._parse_px("") is None)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)