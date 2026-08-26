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

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)