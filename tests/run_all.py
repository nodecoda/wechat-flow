"""统一测试入口：python tests/run_all.py

逐个运行 tests/test_*.py，汇总 PASS/FAIL，任一失败 exit 1。
"""
import io, os, subprocess, sys
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
        ok = r.returncode == 0
        last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        results.append((f.name, ok, last))
        print(f"[{'PASS' if ok else 'FAIL'}] {f.name} — {last}")
        if not ok:
            print(r.stdout[-1500:] if r.stdout else "")
            print(r.stderr[-800:] if r.stderr else "")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} suites passed")
    return 0 if passed == len(results) else 1

if __name__ == "__main__":
    sys.exit(main())
