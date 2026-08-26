"""image_gen.py 回归测试：provider 构造（排版链依赖 PIL，缺失则 SKIP；不触网）。

独立运行：python tests/test_image_gen.py
"""
import io, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "toolkit"))

try:
    import image_gen as ig
except ImportError as e:
    print(f"[SKIP] 依赖缺失（{e}），跳过 image_gen 测试")
    sys.exit(0)

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

# 默认 provider（doubao）缺 api_key → ValueError
try:
    ig._build_provider_from_entry({"provider": "doubao"})
    check("缺 api_key 抛 ValueError", False)
except ValueError:
    check("缺 api_key 抛 ValueError", True)

# 未知 provider → ValueError
try:
    ig._build_provider_from_entry({"provider": "nope", "api_key": "k"})
    check("未知 provider 抛 ValueError", False)
except ValueError:
    check("未知 provider 抛 ValueError", True)

# 合法构造
p = ig._build_provider_from_entry({"provider": "openai", "api_key": "k", "model": "gpt-x"})
check("openai provider 构造", p is not None and "openai" in p.__class__.__name__.lower())

# 尺寸预设：cover 各 provider 预设一致；宽高比归一
check("cover 预设 openai=1792x1024", ig.SIZE_PRESETS["cover"]["openai"] == "1792x1024")
check("_size_to_aspect 16:9", ig._size_to_aspect("1792x1024") == "16:9")
check("_size_to_aspect 透传", ig._size_to_aspect("4:3") == "4:3")
check("_size_to_aspect 非法→16:9", ig._size_to_aspect("xx") == "16:9")

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)