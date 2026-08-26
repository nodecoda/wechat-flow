"""统一测试入口：python tests/run_all.py

逐个运行 tests/test_*.py，汇总 PASS/FAIL/SKIP，任一失败 exit 1。
SKIP：测试文件自检依赖缺失时打印 [SKIP] 并 exit 0（如排版链依赖未安装）。
"""
import io, subprocess, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
TESTS = Path(__file__).resolve().parent

def main():
    files = sorted(p for p in TESTS.glob("test_*.py") if p.name != "run_all.py")
    if not files:
        print("无测试文件")
        return 1
    results = []
    for f in files:
        r = subprocess.run([sys.executable, str(f)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = r.stdout or ""
        skipped = "[SKIP]" in out
        ok = r.returncode == 0
        if ok and skipped:
            status = "SKIP"
        elif ok:
            status = "PASS"
        else:
            status = "FAIL"
        last = out.strip().splitlines()[-1] if out.strip() else ""
        results.append((f.name, status, last))
        print(f"[{status}] {f.name} — {last}")
        if status == "FAIL":
            print(out[-1500:] if out else "")
            print((r.stderr or "")[-800:] if r.stderr else "")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    skipped = sum(1 for _, s, _ in results if s == "SKIP")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"\n{passed} passed / {failed} failed / {skipped} skipped（共 {len(results)} 套件）")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())