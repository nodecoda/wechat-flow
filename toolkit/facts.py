#!/usr/bin/env python3
"""
FactSheet（事实溯源）工具 for WeWrite（Phase D）。

写作的底线是"不编造"。FactSheet 把 Step 3.2 采集到的真实素材登记成一张
可核实、可流转的溯源表（output/<slug>-facts.yaml），并在 Step 4.5 自检时
做引用拦截：文中出现的数字 / 日期 / 具名观点 / 来源声明必须命中 verified
条目，否则报告"疑似未溯源"。

  init       : 建溯源表（空表，或从 --item 批量登记），条目初始 pending
  verify     : 单条状态流转 pending -> verified / rejected
  status     : 汇总与明细（verified / rejected / pending 计数）
  check-refs : 引用拦截——扫描 draft 的强事实信号并与 FactSheet 比对

Usage:
    python3 toolkit/facts.py init {slug} [--item "声明|来源URL|来源名"]...
    python3 toolkit/facts.py verify {slug} --index N --status verified|rejected
    python3 toolkit/facts.py status {slug} [--json]
    python3 toolkit/facts.py check-refs {draft.md} [--facts output/{slug}-facts.yaml] [--json]

Exit codes:
    0  全部已溯源 / 无 FactSheet（跳过拦截）
    1  check-refs 发现疑似未溯源信号
    2  用法错误 / 文件不存在
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

import yaml  # noqa: E402
from wewrite_common import (  # noqa: E402
    load_output_entity,
    output_entity_path,
    save_output_entity,
)

STATUSES = ("pending", "verified", "rejected")
MATCH_MIN = 0.30  # bigram 覆盖度阈值：低于视为"未溯源"

DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
SLUG_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# 强事实信号（复用 scripts/humanness_score.py REAL_SOURCE_PATTERNS 思路并扩展）
FACT_PATTERNS = [
    re.compile(r"\d+(?:\.\d+)?\s*%"),  # 百分比
    re.compile(r"20[12]\d\s*年(?:\s*[0-9]{1,2}\s*月(?:\s*[0-9]{1,2}\s*日)?)?"),  # 日期
    re.compile(r"[\u4e00-\u9fff]{2,4}\s*(?:表示|指出|认为|写道|提到|说过)"),  # 具名观点
    re.compile(r"(?:据|根据|来自)\s*[\u4e00-\u9fff]{2,12}\s*(?:报告|数据|研究|调查|统计|白皮书)"),  # 来源声明
    re.compile(r"\d+(?:\.\d+)?\s*(?:亿|万|千)\s*(?:美元|元|人民币|用户|人|人次|家|台|辆)"),  # 带量级单位
    re.compile(r"(?:超过|达到|突破|增长|下降|占比|约占|高达|只有|仅|近)\s*\d+(?:\.\d+)?\s*(?:%|亿|万|千)?"),  # 比较词+数字
]

TITLE_RE = re.compile(r"^\s*#{1,6}\s")
LIST_RE = re.compile(r"^\s*(?:[-*]|\d+[.、)])\s*")


def _ensure_utf8_stdio():
    """Windows GBK 控制台无法打印 ✓/emoji，强制 stdout/stderr 走 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


_ensure_utf8_stdio()


# ---------------------------------------------------------------------------
# 信号提取
# ---------------------------------------------------------------------------

def _sentence_at(line: str, start: int, end: int) -> str:
    """取信号所在的句子（按。！？；切分），限制长度防止上下文过大。"""
    seg_start = 0
    for s in ("。", "！", "？", "；"):
        pos = line.rfind(s, 0, start)
        if pos >= 0:
            seg_start = max(seg_start, pos + 1)
    seg_end = len(line)
    for s in ("。", "！", "？", "；"):
        pos = line.find(s, end)
        if pos >= 0:
            seg_end = min(seg_end, pos + 1)
    seg = line[seg_start:seg_end].strip()
    if len(seg) > 80:
        mid = (start + end) // 2 - seg_start
        a = max(0, mid - 30)
        b = min(len(seg), mid + 30)
        return ("…" if a > 0 else "") + seg[a:b].strip() + ("…" if b < len(seg) else "")
    return seg


def _claim_windows(text: str) -> list[dict]:
    """扫描强事实信号，返回 [{match, context, line}]，跳过标题行与列表项。"""
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if TITLE_RE.match(line) or LIST_RE.match(line):
            continue
        for pat in FACT_PATTERNS:
            for m in pat.finditer(line):
                hits.append({
                    "match": m.group(0).strip(),
                    "context": _sentence_at(line, m.start(), m.end()),
                    "line": lineno,
                })
    # 去重（同句的多个信号合并为一条，同句不同事实仍只触发一次提示）
    seen = set()
    uniq = []
    for h in hits:
        key = (h["line"], h["context"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)
    return uniq


# ---------------------------------------------------------------------------
# 相似度（字符 bigram，无分词器时的中文近似）
# ---------------------------------------------------------------------------

def _bigrams(text: str) -> list[str]:
    chars = [c for c in str(text) if re.match(r"[\u4e00-\u9fffA-Za-z0-9]", c)]
    return ["".join(pair) for pair in zip(chars, chars[1:])]


def _coverage(needle_bigrams: list[str], hay_bigrams: list[str]) -> float:
    """needle 的 bigram 有多少比例出现在 hay 中（0..1）。"""
    if not needle_bigrams or not hay_bigrams:
        return 0.0
    hay_set = set(hay_bigrams)
    return sum(1 for b in needle_bigrams if b in hay_set) / len(needle_bigrams)


def _best_coverage(ctx: str, claim: str) -> float:
    """双向覆盖度取 max：claim 短而上下文长时仍能命中。"""
    cb, kb = _bigrams(ctx), _bigrams(claim)
    return max(_coverage(cb, kb), _coverage(kb, cb))


# ---------------------------------------------------------------------------
# 路径工具
# ---------------------------------------------------------------------------

def _stem_of_facts(path: Path) -> str:
    stem = path.stem
    if stem.endswith("-facts"):
        stem = stem[: -len("-facts")]
    return stem


def _facts_path_from_draft(draft: Path) -> Path | None:
    stem = draft.stem
    for candidate in (stem, DATE_PREFIX_RE.sub("", stem)):
        p = output_entity_path(candidate, "facts")
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# init / verify / status
# ---------------------------------------------------------------------------

def init_factsheet(slug: str, items: list[tuple[str, str, str]]) -> Path:
    if not SLUG_RE.match(slug):
        raise ValueError("slug 只能包含字母/数字/下划线/连字符")
    data = load_output_entity(slug, "facts")
    existing = [str(i.get("claim", "")) for i in data["items"]]
    added = 0
    for claim, url, name in items:
        claim = claim.strip()
        if not claim:
            continue
        if claim in existing:
            continue
        data["items"].append({
            "claim": claim,
            "source_url": url.strip(),
            "source_name": name.strip(),
            "extracted_at": date.today().isoformat(),
            "status": "pending",
        })
        existing.append(claim)
        added += 1
    path = save_output_entity(slug, "facts", data)
    total = len(data["items"])
    if added:
        print(f"FactSheet 已更新：{path}（新增 {added} 条，共 {total} 条）")
    else:
        print(f"FactSheet 已存在：{path}（{total} 条，无新增）")
    print(f"提示：逐条核实后运行 verify 流转状态（pending -> verified/rejected）。")
    return path


def verify(slug: str, index: int, status: str, as_json: bool = False) -> dict:
    if not SLUG_RE.match(slug):
        raise ValueError("slug 只能包含字母/数字/下划线/连字符")
    if status not in STATUSES:
        raise ValueError(f"--status 必须是 {'/'.join(STATUSES)}")
    data = load_output_entity(slug, "facts")
    items = data["items"]
    if index < 1 or index > len(items):
        raise IndexError(f"--index {index} 越界：FactSheet 共 {len(items)} 条（1-based）")
    item = items[index - 1]
    old = item.get("status", "pending")
    if old == status:
        raise ValueError(f"第 {index} 条已是 {status}，无需重复操作")
    item["status"] = status
    if status == "verified":
        item["verified_at"] = date.today().isoformat()
    if status != "verified":
        item.pop("verified_at", None)
    path = save_output_entity(slug, "facts", data)
    result = {
        "index": index,
        "claim": item["claim"],
        "status": status,
        "path": str(path),
    }
    if as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"[{index}] {item['claim']}")
        print(f"    状态: {old} -> {status}")
    return result


def show_status(slug: str, as_json: bool = False) -> dict:
    if not SLUG_RE.match(slug):
        raise ValueError("slug 只能包含字母/数字/下划线/连字符")
    data = load_output_entity(slug, "facts")
    items = data["items"]
    counts = {s: 0 for s in STATUSES}
    for item in items:
        counts[item.get("status", "pending")] = counts.get(item.get("status", "pending"), 0) + 1
    result = {
        "path": str(output_entity_path(slug, "facts")),
        "total": len(items),
        "counts": counts,
        "items": [
            {
                "index": i + 1,
                "claim": item.get("claim", ""),
                "source_name": item.get("source_name", ""),
                "source_url": item.get("source_url", ""),
                "status": item.get("status", "pending"),
            }
            for i, item in enumerate(items)
        ],
    }
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"FactSheet: {result['path']}")
        print(f"总数 {result['total']} | verified {counts['verified']} | "
              f"rejected {counts['rejected']} | pending {counts['pending']}")
        for it in result["items"]:
            tag = {"verified": "✓", "rejected": "✗", "pending": "·"}.get(it["status"], "·")
            print(f"  {tag} [{it['index']}] {it['claim']}"
                  f"{'  | ' + it['source_name'] if it['source_name'] else ''}")
    return result


# ---------------------------------------------------------------------------
# check-refs（引用拦截）
# ---------------------------------------------------------------------------

def check_references(draft: Path, facts_path: Path | None = None, as_json: bool = False) -> tuple[int, dict]:
    """扫描草稿强事实信号，与 FactSheet 比对。返回 (exit_code, report)。"""
    if not draft.exists():
        raise FileNotFoundError(f"草稿不存在：{draft}")
    fp = facts_path or _facts_path_from_draft(draft)
    if fp is None or not fp.exists():
        report = {"status": "skipped", "reason": "未找到 FactSheet（先运行 facts.py init）"}
        if as_json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print("[跳过] 未找到 FactSheet，跳过引用拦截。如需强制溯源，先运行 facts.py init。")
        return 0, report

    facts = load_output_entity(_stem_of_facts(fp), "facts")
    items = [i for i in facts.get("items", []) if isinstance(i, dict) and i.get("claim")]
    text = draft.read_text(encoding="utf-8")
    signals = _claim_windows(text)

    traced, missing, pending_hits, rejected_hits = [], [], [], []
    for sig in signals:
        best_score, best_item = 0.0, None
        for item in items:
            score = _best_coverage(sig["context"], str(item["claim"]))
            if score > best_score:
                best_score, best_item = score, item
        entry = {
            "line": sig["line"],
            "match": sig["match"],
            "context": sig["context"],
            "score": round(best_score, 2),
        }
        if best_item is None or best_score < MATCH_MIN:
            entry["status"] = "missing"
            missing.append(entry)
        elif best_item.get("status") == "verified":
            entry["status"] = "traced"
            entry["claim"] = str(best_item.get("claim", ""))
            traced.append(entry)
        elif best_item.get("status") == "rejected":
            entry["status"] = "rejected_hit"
            entry["claim"] = str(best_item.get("claim", ""))
            rejected_hits.append(entry)
        else:
            entry["status"] = "pending_hit"
            entry["claim"] = str(best_item.get("claim", ""))
            pending_hits.append(entry)

    report = {
        "status": "ok" if not (missing or pending_hits or rejected_hits) else "issues",
        "facts_path": str(fp),
        "draft": str(draft),
        "signals": len(signals),
        "traced": traced,
        "missing": missing,
        "pending_hits": pending_hits,
        "rejected_hits": rejected_hits,
    }
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return (0 if report["status"] == "ok" else 1), report


def _print_report(report: dict) -> None:
    print("=== FactSheet 引用拦截 ===")
    print(f"FactSheet: {report['facts_path']}")
    print(f"草稿: {report['draft']}（强事实信号 {report['signals']} 处）")
    print()
    if report["traced"]:
        print(f"✅ 已溯源 {len(report['traced'])} 处：")
        for e in report["traced"]:
            print(f"  - line {e['line']} 「{e['context']}」→ 命中「{e['claim']}」（{e['score']}）")
    if report["pending_hits"]:
        print(f"\n⚠️ 命中未核实条目（pending）{len(report['pending_hits'])} 处——先 verify 再定稿：")
        for e in report["pending_hits"]:
            print(f"  - line {e['line']} 「{e['context']}」→ pending 条目「{e['claim']}」")
    if report["rejected_hits"]:
        print(f"\n⛔ 命中已拒绝条目 {len(report['rejected_hits'])} 处——禁止引用，请改写或删除：")
        for e in report["rejected_hits"]:
            print(f"  - line {e['line']} 「{e['context']}」→ rejected 条目「{e['claim']}」")
    if report["missing"]:
        print(f"\n⚠️ 疑似未溯源 {len(report['missing'])} 处：")
        for e in report["missing"]:
            print(f"  - line {e['line']} 「{e['context']}」→ 未命中任何条目（最近相似度 {e['score']}）")
    print()
    if report["status"] == "ok":
        print("结论: 全部已溯源，通过 ✅")
    else:
        n = len(report["missing"]) + len(report["pending_hits"]) + len(report["rejected_hits"])
        print(f"结论: {n} 处待处理 → 回到 Step 3.3 补登记/核实，或改写为模糊表达、删除")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_item(raw: str) -> tuple[str, str, str]:
    parts = raw.split("|")
    claim = parts[0].strip()
    url = parts[1].strip() if len(parts) > 1 else ""
    name = parts[2].strip() if len(parts) > 2 else ""
    return claim, url, name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="facts.py", description="FactSheet（事实溯源）工具：溯源表 + 引用拦截")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="建溯源表（可 --item 批量登记）")
    p_init.add_argument("slug")
    p_init.add_argument("--item", action="append", default=[],
                        help='一条素材，格式 "声明|来源URL|来源名"')

    p_verify = sub.add_parser("verify", help="单条状态流转")
    p_verify.add_argument("slug")
    p_verify.add_argument("--index", type=int, required=True)
    p_verify.add_argument("--status", choices=STATUSES, required=True)
    p_verify.add_argument("--json", action="store_true")

    p_status = sub.add_parser("status", help="汇总与明细")
    p_status.add_argument("slug")
    p_status.add_argument("--json", action="store_true")

    p_check = sub.add_parser("check-refs", help="引用拦截")
    p_check.add_argument("draft", help="草稿 markdown 路径")
    p_check.add_argument("--facts", default=None, help="FactSheet 路径（缺省自动推导）")
    p_check.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "init":
            init_factsheet(args.slug, [_parse_item(i) for i in args.item])
        elif args.cmd == "verify":
            verify(args.slug, args.index, args.status, as_json=args.json)
        elif args.cmd == "status":
            show_status(args.slug, as_json=args.json)
        elif args.cmd == "check-refs":
            code, _ = check_references(Path(args.draft), facts_path=args.facts and Path(args.facts),
                                       as_json=args.json)
            return code
    except (ValueError, IndexError, FileNotFoundError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())