"""ncoda_common.load_history 回归测试：损坏/缺失/非 dict 项降级。

独立运行：python tests/test_history.py
"""
import io, sys, tempfile, shutil
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from ncoda_common import load_history, save_history, normalize_history

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

tmp = Path(tempfile.mkdtemp(prefix="test_history_"))
try:
    # 1. 文件不存在 -> []
    check("缺失文件返回 []", load_history(tmp) == [])

    # 2. 有效文件：dict 保留，非 dict 项被 normalize 过滤
    articles = [
        {"date": "2026-08-26", "title": "甲"},
        {"date": "2026-08-27", "title": "乙"},
    ]
    save_history(articles, tmp)
    loaded = load_history(tmp)
    check("有效文件解析", loaded == articles, f"got {len(loaded)} items")

    # 3. 损坏 YAML（历史遗留：标量混入列表项）-> [] 且不抛异常
    bad = tmp / "history.yaml"
    bad.write_text("- EJuF9wXRAVH0H0Sw_g2unull\n  writing_persona: cold-analyst\n", encoding="utf-8")
    try:
        got = load_history(tmp)
        check("损坏文件降级为 []", got == [], f"got {got!r}")
    except Exception as e:
        check("损坏文件不抛异常", False, f"raised {type(e).__name__}: {e}")

    # 4. normalize_history：dict 包裹（旧格式 articles: []）兼容
    check("dict 包裹兼容", normalize_history({"articles": [{"a": 1}]}) == [{"a": 1}])
    check("非 dict 项过滤", normalize_history([{"a": 1}, "bad", 3, {"b": 2}]) == [{"a": 1}, {"b": 2}])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)
