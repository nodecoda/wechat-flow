#!/usr/bin/env python3
"""WeWrite evals runner — minimal assertion interpreter for evals/evals.json.

Usage:
    python3 evals/run_evals.py                 # run all evals
    python3 evals/run_evals.py --eval 3        # run one eval (repeatable)
    python3 evals/run_evals.py --slug <slug>   # pin slug for {slug} targets
    python3 evals/run_evals.py --json          # machine-readable report
    python3 evals/run_evals.py --list          # list evals + assertions

Exit code: 0 all pass, 1 any assertion failed.

Supported assertion types (schema):
    file_exists     — artifact present (resolved via "target")
    content_check   — target content satisfies predicate (handler by name)
    range_check     — numeric range on extracted value (min/max)
    negative_check  — artifact must NOT exist
    behavior_check  — pluggable runnable handler (command / heuristic)

Zero external deps (stdlib + PyYAML, already in requirements.txt).
"""

import argparse
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml


def _ensure_utf8_stdio():
    """Windows GBK console cannot print Chinese/emoji; force UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


_ensure_utf8_stdio()

SKILL_ROOT = Path(__file__).resolve().parent.parent
EVALS_FILE = Path(__file__).resolve().parent / "evals.json"
OUTPUT_DIR = SKILL_ROOT / "output"
PY = sys.executable
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "toolkit"))
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

KIND_SUFFIXES = ("-intent", "-facts", "-anchors", "-revision")
DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
BANNED_WORDS = ["首先", "其次", "总之", "综上所述", "值得注意的是", "不可否认", "众所周知", "至关重要", "不言而喻"]
BROKEN_MARKERS = ["——", "…", "...", "——"]
DETAIL_PATTERNS = [
    re.compile(r"20[12]\d\s*年"),            # 年份
    re.compile(r"\d{1,2}\s*月\s*\d{1,2}\s*日"),  # 具体日期
    re.compile(r"\d+\.\d+\s*%"),             # 非整数百分比
    re.compile(r"\bL[234]\b"),               # L2/L3/L4
    re.compile(r"[A-Z]{2,}[-\d]*\b"),        # 型号/代号（GB 44721）
    re.compile(r"[\u4e00-\u9fff]{2,8}(?:大学|学院|研究院|公司|集团|教授|博士)"),  # 机构/人物头衔
]
ANCHOR_BLOCK_RE = re.compile(r":::anchor\s*(\w*)\s*\n(.*?)\n:::", re.S)


# ---------------------------------------------------------------------------
# resolution helpers
# ---------------------------------------------------------------------------

def find_slugs():
    slugs = set()
    if not OUTPUT_DIR.is_dir():
        return sorted(slugs)
    for p in OUTPUT_DIR.glob("*.yaml"):
        stem = p.stem
        for suf in KIND_SUFFIXES:
            if stem.endswith(suf):
                stem = stem[: -len(suf)]
                break
        stem = DATE_PREFIX_RE.sub("", stem)
        if stem:
            slugs.add(stem)
    return sorted(slugs)


ACTIVE_SLUG = None  # set via --slug; threads into resolution


def newest_file(pattern):
    if not OUTPUT_DIR.is_dir():
        return None
    files = sorted(OUTPUT_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def newest_article(slug=None):
    """Newest real article md: prefer slug match, exclude test/smoke artifacts."""
    if not OUTPUT_DIR.is_dir():
        return None
    files = sorted(OUTPUT_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if slug:
        for f in files:
            if slug in f.name:
                return f
    for f in files:
        if "test" not in f.stem and "smoke" not in f.stem:
            return f
    return files[0] if files else None


def resolve(target, slug=None):
    """Resolve an assertion target to candidate paths."""
    if not target:
        return []
    t = target.strip()
    slug = slug or ACTIVE_SLUG
    if t in ("article", "md"):
        f = newest_article(slug)
        return [f] if f else []
    if t in ("html", "*.html"):
        f = newest_file("*.html")
        return [f] if f else []
    if "{slug}" in t:
        slugs = [slug] if slug else find_slugs()
        out = []
        for s in slugs:
            rel = str(t).replace("{slug}", s)
            if rel.startswith("output/"):
                rel = rel[len("output/"):]
            q = OUTPUT_DIR / rel
            if q.exists():
                out.append(q)
        return out
    p = Path(t)
    if p.is_absolute():
        return [p] if p.exists() else []
    rel = t[7:] if t.startswith("output/") else t
    out = []
    q = OUTPUT_DIR / rel
    if q.exists():
        out.append(q)
    q2 = SKILL_ROOT / rel
    if q2.exists():
        out.append(q2)
    return out


def read_text(paths, limit=200000):
    for p in paths:
        try:
            return p.read_text(encoding="utf-8")
        except Exception:
            continue
    return ""


def first_path(paths):
    return paths[0] if paths else None


def load_yaml(paths):
    for p in paths:
        try:
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
    return {}


# ---------------------------------------------------------------------------
# handlers
# ---------------------------------------------------------------------------

def _style_fields(a):
    data = load_yaml(resolve(a.get("target", "style.yaml")))
    missing = [k for k in a.get("expect", []) if k not in data]
    return (not missing, f"style.yaml keys missing={missing}")


def _thesis_filled(a):
    data = load_yaml(resolve(a.get("target", "output/{slug}-intent.yaml")))
    thesis = str(data.get("thesis", "")).strip()
    ok = thesis != "" and data.get("status") in ("user_confirmed", "locked")
    return (ok, f"thesis_len={len(thesis)} status={data.get('status')}")


def _facts_verified(a):
    data = load_yaml(resolve(a.get("target", "output/{slug}-facts.yaml")))
    items = data.get("items") or []
    n = sum(1 for it in items if isinstance(it, dict) and it.get("status") == "verified")
    return (n >= 1, f"verified={n} total={len(items)}")


def _anchors_filled(a):
    text = read_text(resolve("article"))
    blocks = list(ANCHOR_BLOCK_RE.finditer(text))
    filled = 0
    for m in blocks:
        content = m.group(2).strip()
        if content and not content.startswith("[") and len(content) > 20:
            filled += 1
    return (filled >= 1, f"anchor_blocks={len(blocks)} filled={filled}")


def _no_banned_words(a):
    text = read_text(resolve(a.get("target", "article")))
    hits = [w for w in BANNED_WORDS if w in text]
    return (not hits, f"banned_hits={hits}")


def _broken_sentences(a):
    text = read_text(resolve(a.get("target", "article")))
    n = sum(text.count(m) for m in BROKEN_MARKERS)
    return (n >= 3, f"broken_markers={n}")


def _specific_details(a):
    text = read_text(resolve(a.get("target", "article")))
    n = sum(len(pat.findall(text)) for pat in DETAIL_PATTERNS)
    return (n >= 3, f"detail_signals={n}")


def _inline_styles_only(a):
    f = newest_article(ACTIVE_SLUG)
    if not f:
        return (False, "no article md in output/")
    try:
        sys.path.insert(0, str(SKILL_ROOT / "toolkit"))
        from converter import WeChatConverter
        res = WeChatConverter(theme_name="professional-clean").convert_file(str(f))
        html = res.html
        has_inline = 'style="' in html
        has_style_tag = "<style" in html
        ok = has_inline and not has_style_tag
        return (ok, f"inline_style={has_inline} style_tag={has_style_tag} html_len={len(html)}")
    except Exception as e:
        return (False, f"converter error: {e}")


def _h1_extracted(a):
    f = newest_article(ACTIVE_SLUG)
    if not f:
        return (False, "no article md in output/")
    try:
        from converter import WeChatConverter
        res = WeChatConverter(theme_name="professional-clean").convert_file(str(f))
        title = (res.title or "").strip()
        ok = title != "" and title not in res.html
        return (ok, f"title={title[:24]!r} title_in_body={title in res.html}")
    except Exception as e:
        return (False, f"converter error: {e}")


def _generic_expect(a):
    paths = resolve(a.get("target"))
    if not paths:
        return (False, f"no target resolved for {a.get('target')}")
    text = read_text(paths)
    missing = [k for k in a.get("expect", []) if k not in text]
    return (not missing, f"missing_substrings={missing}")


CONTENT_HANDLERS = {
    "style_has_required_fields": _style_fields,
    "thesis_filled": _thesis_filled,
    "facts_verified": _facts_verified,
    "anchors_filled": _anchors_filled,
    "no_banned_words": _no_banned_words,
    "has_broken_sentences": _broken_sentences,
    "has_specific_details": _specific_details,
    "inline_styles_only": _inline_styles_only,
    "h1_extracted": _h1_extracted,
}


def _graceful_no_config():
    cfg = SKILL_ROOT / "config.yaml"
    if cfg.exists():
        return (True, "config.yaml present; degradation not needed")
    ex = SKILL_ROOT / "config.example.yaml"
    return (ex.exists(), f"config.yaml missing; config.example.yaml ships={ex.exists()}")


def _dimensions_recorded():
    f = newest_article(ACTIVE_SLUG)
    if not f:
        return (False, "no article md in output/")
    text = f.read_text(encoding="utf-8")
    fp = text.count("我")
    analogy = len(re.findall(r"(?:像|跟)[^。\n]{0,20}(?:一样|差不多|似的)", text))
    ok = fp >= 5 and analogy >= 1
    return (ok, f"heuristic proxy: 第一人称「我」={fp} 类比≈{analogy}")


def _facts_traced():
    f = newest_article(ACTIVE_SLUG)
    if not f:
        return (False, "no article md in output/")
    facts = sorted(OUTPUT_DIR.glob("*-facts.yaml"), key=lambda p: p.stat().st_mtime, reverse=True)
    args = [PY, str(SKILL_ROOT / "toolkit" / "facts.py"), "check-refs", str(f)]
    if facts:
        args += ["--facts", str(facts[0])]
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        detail = (r.stdout or r.stderr or "").strip().replace("\n", " | ")[-200:]
        return (r.returncode == 0, f"exit={r.returncode} {detail}")
    except Exception as e:
        return (False, f"check-refs error: {e}")


BEHAVIOR_HANDLERS = {
    "graceful_no_config": _graceful_no_config,
    "dimensions_recorded": _dimensions_recorded,
    "facts_traced": _facts_traced,
}


# ---------------------------------------------------------------------------
# assertion runners
# ---------------------------------------------------------------------------

def run_assertion(a, slug):
    t = a.get("type")
    name = a.get("name", "?")
    try:
        if t == "file_exists":
            paths = [p for p in (resolve(a.get("target"), slug) or _guess_paths(a, slug)) if p.exists()]
            ok = len(paths) > 0
            detail = "; ".join(str(p) for p in paths[:3]) if ok else f"not found: {a.get('target')}"
        elif t == "negative_check":
            paths = resolve(a.get("target"), slug)
            ok = len(paths) == 0
            detail = f"must-not-exist absent={ok}" if ok else f"forbidden artifact present: {paths[0]}"
        elif t == "range_check":
            f = first_path(resolve(a.get("target", "article")))
            if not f:
                ok, detail = False, "no article md in output/"
            else:
                text = f.read_text(encoding="utf-8")
                cnt = len(re.findall(r"[\u4e00-\u9fff]", text)) + len(re.findall(r"[A-Za-z]+", text))
                lo, hi = a.get("min"), a.get("max")
                if lo is None or hi is None:
                    m = re.search(r"(\d+)\s*[-~至]\s*(\d+)", a.get("description", ""))
                    if m:
                        lo, hi = int(m.group(1)), int(m.group(2))
                ok = (lo is None or cnt >= lo) and (hi is None or cnt <= hi)
                detail = f"chars={cnt} range={lo}-{hi}"
        elif t == "content_check":
            fn = CONTENT_HANDLERS.get(name, lambda a: _generic_expect(a))
            ok, detail = fn(a)
        elif t == "behavior_check":
            fn = BEHAVIOR_HANDLERS.get(name)
            if fn is None:
                ok, detail = False, f"no handler for behavior_check '{name}'"
            else:
                ok, detail = fn()
        else:
            ok, detail = False, f"unknown assertion type {t}"
    except Exception as e:
        ok, detail = False, f"runner error: {e}"
    return (ok, f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}")


def _guess_paths(a, slug):
    """Fallback: derive target from assertion name when no explicit target."""
    text = (a.get("name", "") + " " + a.get("description", ""))
    if "style" in text:
        return resolve("style.yaml")
    if "html" in text:
        return resolve("html")
    if "intent" in text:
        return resolve("output/{slug}-intent.yaml", slug)
    if "facts" in text:
        return resolve("output/{slug}-facts.yaml", slug)
    if "revision" in text:
        return resolve("output/{slug}-revision.yaml", slug)
    if "article" in text or "md" in text or "文章" in text:
        return resolve("article")
    return []


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def load_evals():
    return json.loads(EVALS_FILE.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description="Run WeWrite evals assertions")
    ap.add_argument("--eval", type=int, action="append", help="eval id filter (repeatable)")
    ap.add_argument("--slug", help="pin slug for {slug} targets")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--list", action="store_true", help="list evals and assertions")
    args = ap.parse_args()

    data = load_evals()
    if args.list:
        for ev in data["evals"]:
            print(f"eval {ev['id']}: {ev['name']}")
            for a in ev["assertions"]:
                print(f"    [{a['type']}] {a['name']}")
        return

    ids = set(args.eval or [])
    global ACTIVE_SLUG
    slug = args.slug
    ACTIVE_SLUG = slug
    total = passed = 0
    fails = []
    lines = []
    for ev in data["evals"]:
        if ids and ev["id"] not in ids:
            continue
        lines.append(f"\n=== eval {ev['id']}: {ev['name']} ===")
        for a in ev["assertions"]:
            ok, line = run_assertion(a, slug)
            total += 1
            passed += int(ok)
            if not ok:
                fails.append(f"eval{ev['id']}/{a['name']}")
            lines.append("    " + line)

    report = "\n".join(lines) + f"\n\n{passed}/{total} assertions passed"
    if args.json:
        print(json.dumps({"total": total, "passed": passed, "failed": total - passed,
                          "fails": fails}, ensure_ascii=False, indent=2))
    else:
        print(report)
    sys.exit(0 if total - passed == 0 else 1)


if __name__ == "__main__":
    main()
