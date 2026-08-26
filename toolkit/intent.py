#!/usr/bin/env python3
"""
Intent (立意) tooling for WeWrite (Phase C).

立意是文章的 DNA：一句话核心判断 + 信息差 + 证据 + 边界。
本模块是"立意脚手架"（人机协作）——机器做可判定部分，观点终审留给人：

  scaffold : 生成空 IntentCard（output/<stem>-intent.yaml），有 FactSheet 时预填 evidence
  validate  : 检验三问的机器可判部分（信息差/可信度/边界 + 黑名单 + 选题相关）
  titles    : 从 thesis/info_gap 生成规则化标题候选（SEO 模板，Agent 可再打磨）
  confirm   : 状态 generated -> user_confirmed（用户选定）
  lock      : 状态 user_confirmed -> locked（定型，供框架/写作/修改消费）
  show      : 展示 IntentCard

候选立意句由 Agent 按 references/intent-cards.md 的四形态生成（本工具不含 LLM），
写入 thesis_candidates；终审后 thesis = 选中项。

Usage:
    python3 toolkit/intent.py scaffold {slug} --topic "{选题}" [--facts output/{slug}-facts.yaml]
    python3 toolkit/intent.py validate output/{slug}-intent.yaml [--blacklist "词1,词2"] [--json]
    python3 toolkit/intent.py titles output/{slug}-intent.yaml [--json]
    python3 toolkit/intent.py confirm output/{slug}-intent.yaml
    python3 toolkit/intent.py lock output/{slug}-intent.yaml
    python3 toolkit/intent.py show output/{slug}-intent.yaml [--json]
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402
from wewrite_common import (  # noqa: E402
    _ensure_utf8_stdio,
    ensure_skill_root,
    load_output_entity,
    output_entity_path,
    save_output_entity,
)

SKILL_ROOT = ensure_skill_root()

ANGLES = ("反转", "升维", "预测", "筛选")

TITLE_LIMIT = 28  # 微信标题最佳长度上限（中文字）


_ensure_utf8_stdio()


# ---------------------------------------------------------------------------
# scaffold
# ---------------------------------------------------------------------------

def _intent_path(slug: str) -> Path:
    return output_entity_path(slug, "intent")


def scaffold(slug: str, topic: str, facts_path: str | None = None) -> Path:
    if not topic.strip():
        raise ValueError("--topic 不能为空")
    card = {
        "topic": topic.strip(),
        "thesis": "",
        "angle": "",
        "thesis_candidates": [],
        "info_gap": {"from": "", "to": ""},
        "evidence": [],
        "boundary": "",
        "title_candidates": [],
        "status": "generated",
    }

    # 有 FactSheet 时预填已核实的证据（Phase D 接线点）
    if facts_path:
        fp = Path(facts_path)
        if fp.exists():
            stem = fp.stem
            if stem.endswith("-facts"):
                stem = stem[: -len("-facts")]
            facts = load_output_entity(stem, "facts")
            verified = [i for i in facts.get("items", []) if isinstance(i, dict) and i.get("status") == "verified"]
            for item in verified[:20]:
                card["evidence"].append({
                    "claim": item.get("claim", ""),
                    "source": item.get("source_name", ""),
                    "url": item.get("source_url", ""),
                })
            if verified:
                print(f"从 FactSheet 预填 {len(verified)} 条已核实证据。")

    path = save_output_entity(slug, "intent", card)
    print(f"IntentCard 已创建：{path}")
    print("下一步：")
    print("  1. 按 references/intent-cards.md 的四形态生成 3-5 个候选判断句，写入 thesis_candidates")
    print("  2. 填 info_gap（from/to）、boundary，终审 thesis")
    print("  3. python3 toolkit/intent.py validate <card>   # 检验三问（机器可判部分）")
    print("  4. python3 toolkit/intent.py lock <card>       # 定型")
    return path


# ---------------------------------------------------------------------------
# validate（检验三问的机器可判部分）
# ---------------------------------------------------------------------------

def _load_style_blacklist() -> list[str]:
    """从 style.yaml 读取黑名单（words + topics）。"""
    style_path = SKILL_ROOT / "style.yaml"
    words: list[str] = []
    if style_path.exists():
        data = load_yaml_safe(style_path)
        if isinstance(data, dict):
            bl = data.get("blacklist", {})
            if isinstance(bl, dict):
                for key in ("words", "topics"):
                    val = bl.get(key, [])
                    if isinstance(val, list):
                        words.extend(str(w) for w in val)
    return words


def load_yaml_safe(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _check_blacklist(card: dict, blacklist: list[str]) -> list[str]:
    hits = []
    haystacks = [str(card.get("topic", "")), str(card.get("thesis", ""))]
    for w in blacklist:
        w = str(w).strip()
        if not w:
            continue
        for hay in haystacks:
            if w and w in hay:
                hits.append(w)
                break
    return hits


def _content_bigrams(text: str) -> set[str]:
    chars = [c for c in str(text) if re.match(r"[\u4e00-\u9fffA-Za-z0-9]", c)]
    return {"".join(pair) for pair in zip(chars, chars[1:])}


def validate(card_path: str, extra_blacklist: str | None = None, as_json: bool = False) -> bool:
    path = Path(card_path)
    if not path.exists():
        raise FileNotFoundError(f"IntentCard 不存在：{path}（先运行 scaffold）")
    stem = path.stem
    if stem.endswith("-intent"):
        stem = stem[: -len("-intent")]
    card = load_output_entity(stem, "intent")

    blacklist = _load_style_blacklist()
    if extra_blacklist:
        blacklist.extend(w.strip() for w in extra_blacklist.split(",") if w.strip())
    blacklist = list(dict.fromkeys(blacklist))  # 去重保序

    results = []  # (question, passed, detail)

    # 信息差（决策 3）：from/to 非空且不同
    gap = card.get("info_gap") or {}
    f, t = str(gap.get("from", "")).strip(), str(gap.get("to", "")).strip()
    if not f or not t:
        results.append(("信息差", False, "info_gap.from / to 均需填写（读者从 X 到 Y 的认知变化）"))
    elif f == t:
        results.append(("信息差", False, "info_gap.from 与 to 相同——没有认知变化，立意不成立"))
    else:
        results.append(("信息差", True, f"from「{f}」→ to「{t}」"))

    # 可信度（决策 5 弱校验）：证据非空
    evidence = [e for e in card.get("evidence", []) if isinstance(e, dict) and e.get("claim")]
    if not evidence:
        results.append(("可信度", False, "evidence 为空——读者凭什么信你？补数据/案例/出处"))
    else:
        results.append(("可信度", True, f"{len(evidence)} 条证据"))

    # 边界：非空
    boundary = str(card.get("boundary", "")).strip()
    if not boundary:
        results.append(("边界", False, "boundary 为空——什么情况下这个判断不成立？"))
    else:
        results.append(("边界", True, boundary[:40]))

    # 立意句：thesis 非空
    thesis = str(card.get("thesis", "")).strip()
    if not thesis:
        results.append(("立意句", False, "thesis 为空——先终审候选，写入核心判断"))
    else:
        results.append(("立意句", True, thesis[:40]))

    # 黑名单
    hits = _check_blacklist(card, blacklist)
    if hits:
        results.append(("黑名单", False, f"命中禁用词：{'、'.join(hits)}——直接淘汰"))
    else:
        results.append(("黑名单", True, f"未命中（检查 {len(blacklist)} 项）"))

    # 选题相关（软校验）
    if thesis and card.get("topic"):
        overlap = _content_bigrams(card["topic"]) & _content_bigrams(thesis)
        if overlap:
            results.append(("选题相关", True, "thesis 与 topic 词面相关"))
        else:
            results.append(("选题相关", False, "thesis 与 topic 无词面重叠——人工核对是否跑题"))
    else:
        results.append(("选题相关", True, "跳过（topic/thesis 未齐）"))

    # 候选完整性（软校验）
    candidates = [c for c in card.get("thesis_candidates", []) if str(c).strip()]
    if candidates:
        results.append(("候选完整性", True, f"{len(candidates)} 个候选"))
    else:
        results.append(("候选完整性", False, "thesis_candidates 为空——建议先按四形态生成候选（可跳过）"))

    blocking = [r for r in results if not r[1] and r[0] in ("信息差", "可信度", "边界", "立意句", "黑名单")]
    passed = len(blocking) == 0

    if as_json:
        print(json.dumps({
            "passed": passed,
            "blacklist_checked": blacklist,
            "questions": [{"question": q, "passed": p, "detail": d} for q, p, d in results],
        }, ensure_ascii=False, indent=2))
    else:
        for q, p, d in results:
            mark = "✓" if p else "✗"
            print(f"  {mark} {q}：{d}")
        print(f"结果：{'通过（可 lock 定型）' if passed else '未通过——修复上述 ✗ 项后重新 validate'}")
    return passed


# ---------------------------------------------------------------------------
# titles（规则化标题候选）
# ---------------------------------------------------------------------------

def _strip_belief_prefix(s: str) -> str:
    """去掉 info_gap 里常见的认知前缀，避免"你以为读者以为…"叠床架屋。"""
    for prefix in ("读者以为", "大家以为", "很多人以为", "你以为", "大家都觉得", "主流观点认为"):
        if s.startswith(prefix):
            return s[len(prefix):]
    return s


def _cjk_latin_space(s: str) -> str:
    """CJK 与拉丁字母/数字之间补空格（与 converter 的排版规则一致）。"""
    s = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9])", r"\1 \2", s)
    s = re.sub(r"([A-Za-z0-9])([\u4e00-\u9fff])", r"\1 \2", s)
    return s


def _trim_title(s: str, limit: int = TITLE_LIMIT) -> str:
    s = _cjk_latin_space(re.sub(r"\s+", " ", s)).strip(" ，。！？")
    if len(s) <= limit:
        return s
    # 优先在标点处截断
    cut = max(s.rfind(p, 0, limit) for p in "，。！？：;；") if s[:limit] else 0
    if cut > limit * 0.5:
        return s[:cut] + "…"
    return s[: limit - 1] + "…"


def suggest_titles(card: dict) -> list[str]:
    thesis = str(card.get("thesis", "")).strip()
    gap = card.get("info_gap") or {}
    f, t = str(gap.get("from", "")).strip(), str(gap.get("to", "")).strip()
    angle = str(card.get("angle", "")).strip()
    titles = []

    # 去掉 info_gap 的认知前缀后再套模板
    f_core = _strip_belief_prefix(f)
    t_core = _strip_belief_prefix(t)

    if thesis:
        titles.append(_trim_title(thesis))                       # 直接判断式
        core = _trim_title(thesis, 18)
        if t_core:
            titles.append(_trim_title(f"{t_core}，{core}"))       # 标签式
            titles.append(_trim_title(f"凭什么{t_core}？"))       # 提问式
    if f_core and t_core and f_core != t_core:
        titles.append(_trim_title(f"你以为{f_core}，其实{t_core}"))  # 反差式（信息差）
        titles.append(_trim_title(f"别再把{f_core}当{t_core}了"))    # 反直觉式
    if angle == "反转" and t_core:
        titles.append(_trim_title(f"都在说{t_core}，但没人提另一面"))  # 反转式
    if angle == "筛选":
        titles.append(_trim_title(f"不是所有人都该{t_core}"))        # 筛选式

    # 去重保序
    seen, out = set(), []
    for x in titles:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out[:5]


def titles(card_path: str, as_json: bool = False) -> list[str]:
    path = Path(card_path)
    stem = path.stem
    if stem.endswith("-intent"):
        stem = stem[: -len("-intent")]
    card = load_output_entity(stem, "intent")
    result = suggest_titles(card)
    card["title_candidates"] = result
    save_output_entity(stem, "intent", card)
    if as_json:
        print(json.dumps({"title_candidates": result}, ensure_ascii=False, indent=2))
    else:
        print("标题候选（规则模板，可按 seo-rules.md 打磨）：")
        for i, t in enumerate(result, 1):
            print(f"  {i}. {t}")
    return result


# ---------------------------------------------------------------------------
# status 流转
# ---------------------------------------------------------------------------

def _load_card(card_path: str) -> tuple[str, dict]:
    path = Path(card_path)
    if not path.exists():
        raise FileNotFoundError(f"IntentCard 不存在：{path}")
    stem = path.stem
    if stem.endswith("-intent"):
        stem = stem[: -len("-intent")]
    return stem, load_output_entity(stem, "intent")


def set_status(card_path: str, target: str) -> None:
    stem, card = _load_card(card_path)
    order = {"generated": 0, "user_confirmed": 1, "locked": 2}
    cur = card.get("status", "generated")
    if order.get(target, -1) < order.get(cur, 0):
        raise ValueError(f"状态回退不允许：{cur} -> {target}")
    card["status"] = target
    save_output_entity(stem, "intent", card)
    print(f"IntentCard 状态：{cur} -> {target}（{Path(card_path)}）")


def show(card_path: str, as_json: bool = False) -> None:
    stem, card = _load_card(card_path)
    if as_json:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return
    print(f"IntentCard（{Path(card_path)}）status={card.get('status')}")
    for key in ("topic", "thesis", "angle", "info_gap", "evidence", "boundary", "title_candidates", "thesis_candidates"):
        val = card.get(key)
        if key in ("evidence", "title_candidates", "thesis_candidates"):
            print(f"  {key}: {len(val) if isinstance(val, list) else val} 项")
            for item in (val or [])[:5]:
                if isinstance(item, dict):
                    print(f"      - {str(item.get('claim', item))[:60]}")
                else:
                    print(f"      - {str(item)[:60]}")
        else:
            print(f"  {key}: {str(val)[:80]}")


def main():
    parser = argparse.ArgumentParser(prog="intent", description="WeWrite 立意脚手架（人机协作）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sc = sub.add_parser("scaffold", help="生成空 IntentCard（有 FactSheet 时预填证据）")
    p_sc.add_argument("slug", help="文章 slug（output/<slug>-intent.yaml）")
    p_sc.add_argument("--topic", required=True, help="选题")
    p_sc.add_argument("--facts", help="FactSheet 路径（output/<slug>-facts.yaml，可选）")

    p_va = sub.add_parser("validate", help="检验三问机器可判部分")
    p_va.add_argument("card", help="IntentCard 路径")
    p_va.add_argument("--blacklist", help="额外禁用词（逗号分隔）")
    p_va.add_argument("--json", action="store_true")

    p_ti = sub.add_parser("titles", help="生成规则化标题候选")
    p_ti.add_argument("card", help="IntentCard 路径")
    p_ti.add_argument("--json", action="store_true")

    p_co = sub.add_parser("confirm", help="状态 -> user_confirmed")
    p_co.add_argument("card", help="IntentCard 路径")
    p_lo = sub.add_parser("lock", help="状态 -> locked（定型）")
    p_lo.add_argument("card", help="IntentCard 路径")
    p_sh = sub.add_parser("show", help="展示 IntentCard")
    p_sh.add_argument("card", help="IntentCard 路径")
    p_sh.add_argument("--json", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "scaffold":
            scaffold(args.slug, args.topic, facts_path=args.facts)
        elif args.command == "validate":
            ok = validate(args.card, extra_blacklist=args.blacklist, as_json=args.json)
            sys.exit(0 if ok else 1)
        elif args.command == "titles":
            titles(args.card, as_json=args.json)
        elif args.command == "confirm":
            set_status(args.card, "user_confirmed")
        elif args.command == "lock":
            set_status(args.card, "locked")
        elif args.command == "show":
            show(args.card, as_json=args.json)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)  # 输入缺失（降级路径），区别于校验失败 exit1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()