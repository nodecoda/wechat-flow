"""theme.py 回归测试：主题加载与列表（排版链依赖，缺失则 SKIP）。

独立运行：python tests/test_theme.py
"""
import io, sys, tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "toolkit"))

try:
    import theme as theme_mod
except ImportError as e:
    print(f"[SKIP] 依赖缺失（{e}），跳过 theme 测试")
    sys.exit(0)

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

# 临时主题目录
tmp = tempfile.mkdtemp(prefix="theme_")
try:
    (Path(tmp) / "my-theme.yaml").write_text(
        "name: my-theme\ndescription: 测试主题\nbase_css: 'p{color:#333}'\ncolors:\n  primary: '#ff0000'\n",
        encoding="utf-8",
    )
    (Path(tmp) / "other.yml").write_text(
        "name: other\ndescription: 另一个\nbase_css: ''\ncolors: {}\n", encoding="utf-8",
    )
    (Path(tmp) / "bad.yaml").write_text("name: no-desc\nbase_css: ''\n", encoding="utf-8")

    names = theme_mod.list_themes(tmp)
    check("list_themes 排序（含 bad.yaml）", names == ["bad", "my-theme", "other"], str(names))
    check("list_themes 排除坏文件? 含 my-theme", "my-theme" in names)
    check("list_themes 空目录", theme_mod.list_themes(str(Path(tmp) / "nope")) == [])

    th = theme_mod.load_theme("my-theme", themes_dir=tmp)
    check("load_theme name", th.name == "my-theme")
    check("load_theme colors", th.colors.get("primary") == "#ff0000")
    check("load_theme base_css", th.base_css)

    try:
        theme_mod.load_theme("missing", themes_dir=tmp)
        check("缺失主题抛 FileNotFoundError", False)
    except FileNotFoundError:
        check("缺失主题抛 FileNotFoundError", True)

    try:
        theme_mod.load_theme("bad", themes_dir=tmp)
        check("缺字段抛 ValueError", False)
    except ValueError:
        check("缺字段抛 ValueError", True)
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)