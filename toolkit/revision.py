#!/usr/bin/env python3
"""
Four-layer revision tooling for WeWrite (Phase B).

初稿是把话说出来，修改是把话说好。修改必须从大到小：
    结构层 → 段落层 → 句子层 → 措辞层
（否则在句子上精雕细琢、回头发现段落要删，是纯浪费。）

本模块是"修改脚手架"（检测/建议/机械修复），不替代人工判断：
  analyze : 四层静态检查，产出 RevisionReport（output/<stem>-revision.yaml）
  apply   : 自动执行措辞层机械修复（空话/全半角数字/重复标点/重复行），改前备份
  recheck : 改后复检（humanness composite 前后对比 + 参数级差异）
  rollback: 恢复 apply 前的备份（防过度修改）

Usage:
    python3 toolkit/revision.py analyze article.md [--intent output/x-intent.yaml] [--json]
    python3 toolkit/revision.py apply   article.md [--dry-run]
    python3 toolkit/revision.py recheck article.md [--json]
    python3 toolkit/revision.py rollback article.md
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")


def _entity_stem(markdown_path) -> str:
    """实体 key：去日期前缀的 slug（与 intent/facts 命名对齐）。"""
    stem = Path(markdown_path).stem
    return DATE_PREFIX_RE.sub("", stem)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wewrite_common import (  # noqa: E402
    _ensure_utf8_stdio,
    ensure_skill_root,
    load_output_entity,
    output_entity_path,
    save_output_entity,
)

SKILL_ROOT = ensure_skill_root()
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import humanness_score as hs  # noqa: E402


_ensure_utf8_stdio()

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 句子开头的空话/套话（删除安全）：避免"首先/其次/最后"这类列举词（可能合法），
# 只处理语义为空的过渡套话。
FILLER_PHRASES = [
    "总而言之", "综上所述", "由此可见", "与此同时", "不难发现",
    "不可否认", "毋庸置疑", "众所周知", "值得注意的是", "需要注意的是",
    "需要指出的是", "事实上", "显而易见", "可以说",
]

# 与 humanness_score.BANNED_WORDS 同源的禁用词（AI 腔）：仅报告，不自动删
AI_FLAVOR_WORDS = [
    "首先", "其次", "再者", "总之", "综上所述", "总而言之",
    "此外", "另外", "与此同时", "不仅如此", "更重要的是",
    "作为一个", "让我们", "值得注意", "需要指出", "不可否认",
    "毋庸置疑", "众所周知", "事实上", "显而易见", "可以说",
    "非常重要", "至关重要", "不言而喻", "具有重要意义",
    "引发了广泛关注", "引起了热烈讨论", "总的来说", "综合来看",
]

STOPWORDS = set(
    "的了是在和与就都也很我你他她它这那有不要会能对从为被把让给"
    "一个之其及等还正上于而或但若如所与"
)

PARA_LIKE_LENGTH_DELTA = 20   # 段落节奏：相邻段长度差阈值（字符）
PARA_MAX_LENGTH = 400         # 超长段阈值
SENT_LIKE_LENGTH_DELTA = 5    # 句子节奏：连续句长度差阈值（writing-guide 1.1）
SENT_MAX_LENGTH = 60          # 超长句阈值
REPEAT_BIGRAM_THRESHOLD = 6   # 内容二元组重复次数阈值
PARA_SIMILAR_RATIO = 0.85     # 相邻段相似度阈值（疑似重复）
H2_MIN_BODY_CHARS = 60        # H2 节最小正文长度

IMPACT_ORDER = {"structure": 0, "paragraph": 1, "sentence": 2, "wording": 3}


# ---------------------------------------------------------------------------
# 文本工具
# ---------------------------------------------------------------------------

def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?…])", text)
    return [p.strip() for p in parts if p.strip()]


def _line_number(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _char_len(s: str) -> int:
    return len(re.sub(r"\s", "", s))


def _content_bigrams(text: str) -> list[str]:
    """去停用词后的连续字符二元组（无分词器时的近似词）。"""
    chars = [c for c in text if re.match(r"[\u4e00-\u9fffA-Za-z0-9]", c) and c not in STOPWORDS]
    return ["".join(pair) for pair in zip(chars, chars[1:])]


def _finding(layer: str, location: str, issue: str, fix: str, impact: str) -> dict:
    return {"layer": layer, "location": location, "issue": issue, "fix": fix, "impact": impact}


def _loc_of(text: str, needle: str, start: int = 0) -> str:
    pos = text.find(needle, start)
    if pos < 0:
        return "?"
    return f"line {_line_number(text, pos)}"


# ---------------------------------------------------------------------------
# 措辞层（全自动规则 + 报告）
# ---------------------------------------------------------------------------

def check_wording(text: str) -> list[dict]:
    findings = []
    # 1) 空话套话
    for phrase in FILLER_PHRASES:
        for m in re.finditer(re.escape(phrase), text):
            before = text[max(0, m.start() - 2):m.start()]
            # 仅报告（apply 时只删句首/逗号后的套话）
            findings.append(_finding(
                "wording", _loc_of(text, m.group(0), m.start()),
                f"空话：{phrase}",
                "删除（若在句首/逗号后，apply 会自动删）", "low"))
    # 2) AI 腔禁用词（与 humanness 2.1 同源）
    for word in AI_FLAVOR_WORDS:
        if word in text:
            findings.append(_finding(
                "wording", _loc_of(text, word),
                f"AI 腔词：{word}",
                "换成更口语/具体的表达，或直接删", "medium"))
    # 3) 重复词（内容二元组频次）
    bigrams = _content_bigrams(text)
    counts = {}
    for b in bigrams:
        counts[b] = counts.get(b, 0) + 1
    for b, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        if n >= REPEAT_BIGRAM_THRESHOLD:
            findings.append(_finding(
                "wording", _loc_of(text, b),
                f"重复表达：{b} 出现 {n} 次",
                "换同义词或调整句式，避免机械复现", "medium"))
            break  # 只报最严重的一处，避免刷屏
    # 4) 一致性：全/半角数字混用
    if re.search(r"[０-９]", text) and re.search(r"[0-9]", text):
        findings.append(_finding(
            "wording", _loc_of(text, re.search(r"[０-９]", text).group(0)),
            "数字全/半角混用",
            "统一为半角（apply 会自动修复）", "low"))
    # 5) 一致性：成对符号失衡
    for open_c, close_c, name in [("「", "」", "直角引号"), ("“", "”", "弯引号"), ("（", "）", "括号"), ("(", ")", "半角括号")]:
        if text.count(open_c) != text.count(close_c):
            findings.append(_finding(
                "wording", _loc_of(text, open_c) if open_c in text else "?",
                f"{name}不成对（{text.count(open_c)} vs {text.count(close_c)}）",
                "补齐或删除多余符号", "low"))
    return findings


def apply_wording_fixes(text: str) -> tuple[str, list[str]]:
    """机械修复措辞层问题。返回（修改后文本, 变更日志）。"""
    log = []

    # 1) 删句首/逗号后的空话套话（保留句中的，避免破坏语法）
    for phrase in FILLER_PHRASES:
        # MULTILINE 使 ^ 匹配段落开头（换行之后），覆盖"段落首行的套话"
        pattern = re.compile(r"(^|[，。；！？])\s*(" + re.escape(phrase) + r")(?=[，,])", re.MULTILINE)
        n = 0
        while n < 1000:  # 安全上限，防止意外死循环
            m = pattern.search(text)
            if not m:
                break
            n += 1
            # 保留分隔符（组1），删除短语（组2）
            text = text[:m.start(1)] + m.group(1) + text[m.end(2):]
        if n:
            log.append(f"删除空话 '{phrase}' x{n}")

    # 1b) 清理删除后残留的跨标点（"。，" "；，" "换行+逗号"等）
    text, n1 = re.subn(r"[。；！？]，", lambda m: m.group(0)[0], text)
    if n1:
        log.append(f"清理标点粘连 x{n1}")
    text, n2 = re.subn(r"(^|\n)，", r"\1", text)
    if n2:
        log.append(f"清理行首逗号 x{n2}")

    # 2) 全角数字 → 半角
    def to_half(m):
        return str(int(m.group(0).translate(str.maketrans("０１２３４５６７８９", "0123456789"))))
    new_text, n = re.subn(r"[０-９]+", to_half, text)
    if n:
        log.append(f"全角数字转半角 x{n}")
        text = new_text

    # 3) 重复标点
    for punc in "，。、；：！？":
        new_text, n = re.subn(re.escape(punc) + "{2,}", punc, text)
        if n:
            log.append(f"折叠重复标点 '{punc}' x{n}")
            text = new_text

    # 4) 连续重复行（整行内容相同）
    lines = text.split("\n")
    dedup, n = [], 0
    for i, line in enumerate(lines):
        if i > 0 and line.strip() and line.strip() == lines[i - 1].strip():
            n += 1
            continue
        dedup.append(line)
    if n:
        log.append(f"删除连续重复行 x{n}")
        text = "\n".join(dedup)

    # 5) 行尾空白
    new_text, n = re.subn(r"[ \t]+$", "", text, flags=re.MULTILINE)
    if n:
        log.append(f"清理行尾空白 x{n}")
        text = new_text

    return text, log


# ---------------------------------------------------------------------------
# 句子层（报告）
# ---------------------------------------------------------------------------

def check_sentences(text: str) -> list[dict]:
    findings = []
    sents = [s for s in _sentences(text) if _char_len(s) > 1]
    # 连续 ≥3 句长度相近（±5 字）
    run = []
    for i, s in enumerate(sents):
        if run and abs(_char_len(s) - _char_len(sents[i - 1])) <= SENT_LIKE_LENGTH_DELTA:
            run.append(s)
        else:
            run = [s]
        if len(run) == 3:
            findings.append(_finding(
                "sentence", _loc_of(text, run[0]),
                "连续 3 句长度相近（节奏平）",
                "把其中 1 句拆短或并入长句", "medium"))
            run = []
    # 超长句
    for s in sents:
        if _char_len(s) > SENT_MAX_LENGTH:
            findings.append(_finding(
                "sentence", _loc_of(text, s),
                f"超长句（{_char_len(s)} 字）",
                "拆成 2 句或加逗号断句", "medium"))
    return findings


# ---------------------------------------------------------------------------
# 段落层（报告）
# ---------------------------------------------------------------------------

def check_paragraphs(text: str) -> list[dict]:
    findings = []
    paras = _paragraphs(text)
    # 连续 2 段长度相近
    for i in range(1, len(paras)):
        if abs(_char_len(paras[i]) - _char_len(paras[i - 1])) <= PARA_LIKE_LENGTH_DELTA:
            findings.append(_finding(
                "paragraph", f"line {_line_number(text, text.find(paras[i]))}",
                "连续 2 段长度相近（节奏平）",
                "其中一段加长或缩短，制造长短交替", "medium"))
            break
    # 超长段
    for p in paras:
        if _char_len(p) > PARA_MAX_LENGTH:
            findings.append(_finding(
                "paragraph", _loc_of(text, p),
                f"超长段（{_char_len(p)} 字）",
                "按逻辑拆成 2-3 段", "medium"))
    # 相邻段疑似重复
    for i in range(1, len(paras)):
        a, b = paras[i - 1], paras[i]
        if a and b and difflib.SequenceMatcher(None, a, b).ratio() >= PARA_SIMILAR_RATIO:
            findings.append(_finding(
                "paragraph", _loc_of(text, b),
                "相邻段疑似重复表述",
                "合并或删掉其中一段", "high"))
            break
    return findings


# ---------------------------------------------------------------------------
# 结构层（报告；立意贯穿需要 IntentCard）
# ---------------------------------------------------------------------------

def check_structure(text: str, intent: dict | None) -> list[dict]:
    findings = []
    h1s = re.findall(r"^#\s+.+$", text, flags=re.MULTILINE)
    h2s = re.findall(r"^##\s+.+$", text, flags=re.MULTILINE)
    if not h1s:
        findings.append(_finding("structure", "?", "缺少 H1 标题", "补 H1（20-28 字）", "high"))
    elif len(h1s) > 1:
        findings.append(_finding("structure", _loc_of(text, h1s[1]), "存在多个 H1", "只保留一个", "medium"))
    if len(h2s) < 2:
        findings.append(_finding("structure", "?", "H2 少于 2 个（结构单薄）", "用框架补足 3-5 个 H2 板块", "medium"))

    # H2 节过薄
    lines = text.split("\n")
    h2_pos = [i for i, ln in enumerate(lines) if ln.strip().startswith("## ")]
    for idx, pos in enumerate(h2_pos):
        end = h2_pos[idx + 1] if idx + 1 < len(h2_pos) else len(lines)
        body = "\n".join(lines[pos + 1:end])
        if _char_len(body) < H2_MIN_BODY_CHARS:
            findings.append(_finding(
                "structure", f"line {pos + 1}（{lines[pos].strip()}）",
                "H2 节正文过薄",
                "补充素材/案例，或考虑删节", "medium"))

    # 首尾呼应（开头段 vs 结尾段的词面重叠）
    paras = _paragraphs(text)
    if len(paras) >= 3:
        first, last = _content_bigrams(paras[0]), _content_bigrams(paras[-1])
        if first and last and not (set(first) & set(last)):
            findings.append(_finding(
                "structure", _loc_of(text, paras[-1]),
                "结尾与开头无词面呼应",
                "回扣开头的钩子/立意，制造闭环感", "low"))

    # 立意贯穿（有 IntentCard 时）
    if intent and intent.get("thesis"):
        thesis_bigrams = set(_content_bigrams(intent["thesis"]))
        if thesis_bigrams:
            missing = []
            for idx, pos in enumerate(h2_pos):
                end = h2_pos[idx + 1] if idx + 1 < len(h2_pos) else len(lines)
                body = "\n".join(lines[pos + 1:end])
                if thesis_bigrams and not (thesis_bigrams & set(_content_bigrams(body))):
                    missing.append(lines[pos].strip())
            if missing:
                findings.append(_finding(
                    "structure", _loc_of(text, text.split("\n")[h2_pos[0]]) if h2_pos else "?",
                    f"以下 H2 节未见立意关键词：{', '.join(missing[:3])}",
                    "人工核对是否偏离核心论点（立意是 DNA）", "medium"))
    return findings


# ---------------------------------------------------------------------------
PARAM_THRESHOLD = 0.65  # 参数分低于此值生成修改建议（0=差, 1=好）

# 参数层（第五层）：humanness 检测指标 → 可执行修改建议
# 打通"评分"与"修改"：Score 只告诉你哪里低，这里告诉你具体怎么改。
PARAM_FIXES = {
    "negative_emotion_floor": {
        "issue": "负面情绪占比不足",
        "fix": "负面句占比目标 ≥20%（检测器按句命中词表）。在吐槽/质疑/担忧处加入负面表达，"
               "可用词：失望、坑、忽悠、套路、离谱、不靠谱、受够了、没戏、凉了、白搭、割韭菜、画大饼、扯",
        "example": "「说实话，这块我挺担忧的。」/「这套路我熟，跟减肥药广告一个路子。」",
    },
    "sentence_variance": {
        "issue": "句长方差不足（AI 句长均匀）",
        "fix": "插入 1-5 字超短句（「嗯。」「就这？」「悬着。」），且紧邻 40+ 字长句制造落差；"
               "避免连续 3 句相近长度（±5 字）",
        "example": "「就这？嗯。没那么简单。」",
    },
    "word_temperature_bias": {
        "issue": "词汇温度带不足（冷/温/热/野需 ≥3 带）",
        "fix": "同一段混搭四温度：冷=信息不对称、结构性、护城河；温=说实话、说白了、懂的都懂；"
               "热=卷、破防、格局打开；野=整挺好、瞎折腾、扯",
        "example": "「这种信息不对称，八成是普通人买单。」",
    },
    "paragraph_rhythm": {
        "issue": "段落节奏平（连续相近长度段落）",
        "fix": "穿插 1 句短段（强调/转折/吐槽）；长段 ≤150 字；禁止连续 2 段长度 ±20 字相近",
        "example": "长段后接「但你先别急着点赞。」",
    },
    "broken_sentence_rate": {
        "issue": "破句/不完整句不足",
        "fix": "加入破句结构：自我纠正、破折号中断（「这个落差——」）、独立超短句、反问独句",
        "example": "「不对，准确说是等保险公司先想明白。」",
    },
    "self_correction_rate": {
        "issue": "自我纠正/插入语不足",
        "fix": "加入 1-2 处自我纠正或插入语（「不对」「准确说」「——注意，是 X，不是 Y」）",
        "example": "「——注意，是行政违法责任，不是事故赔偿责任。」",
    },
    "adverb_density": {
        "issue": "副词密度过高",
        "fix": "每 100 字副词 ≤3 个；用具体描述替代副词（「非常快地增长」→「三个月翻了一番」）",
        "example": "把「非常/十分/特别」换成具体数字或场景",
    },
    "real_data_density": {
        "issue": "真实数据/来源引用不足",
        "fix": "每 H2 段嵌入真实素材（数字/具名来源），用「据…数据/报告」句式；素材须命中 FactSheet",
        "example": "「据公开数据显示，渗透率已达 70.5%。」（跑 facts.py check-refs 验证）",
    },
}


def check_params(scored: dict) -> list[dict]:
    """参数层：humanness 低分指标 → 可执行修改建议（评分与修改的桥梁）。

    同一参数可能由多个检测项（如 sentence_variance = stddev + range）构成，
    按参数聚合、取最低分项，避免重复建议。
    """
    worst: dict[str, dict] = {}
    for tier_name in ("tier1", "tier2"):
        tier = scored.get(tier_name, {})
        for name, data in tier.items():
            if name.startswith("_"):
                continue
            param = data.get("param")
            if not param or param not in PARAM_FIXES:
                continue
            if data["score"] >= PARAM_THRESHOLD:
                continue
            if param not in worst or data["score"] < worst[param]["score"]:
                worst[param] = {
                    "name": name, "score": data["score"], "detail": data.get("detail", "")}
    findings = []
    for param, w in sorted(worst.items()):
        info = PARAM_FIXES[param]
        findings.append(_finding(
            "param",
            f"{param} ({w['score']:.2f})",
            f"{info['issue']}：{w['detail']}",
            f"{info['fix']} 示例：{info['example']}",
            "high" if w["score"] < 0.4 else "medium"))
    return findings


# ---------------------------------------------------------------------------
# 金句候选（报告）
# ---------------------------------------------------------------------------

GOLDEN_MARKERS = ("判断", "本质", "核心", "关键是", "说白了", "说到底", "最重要", "从来不", "我的判断", "别", "骗", "坑", "错")

def find_golden_sentence_candidates(text: str) -> list[str]:
    sents = [s for s in _sentences(text) if 12 <= _char_len(s) <= 40 and not s.lstrip().startswith("#")]
    hits = [s for s in sents if any(m in s for m in GOLDEN_MARKERS)]
    return hits[:5]


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _revision_path(markdown_path: str) -> Path:
    return output_entity_path(Path(markdown_path).stem, "revision")


def analyze(markdown_path: str, intent_path: str | None = None, as_json: bool = False) -> dict:
    path = Path(markdown_path)
    text = path.read_text(encoding="utf-8")
    intent = {}
    if intent_path:
        ip = Path(intent_path)
        if ip.exists():
            stem = ip.stem
            if stem.endswith("-intent"):
                stem = stem[: -len("-intent")]
            intent = load_output_entity(stem, "intent")

    # baseline（复检基准）：humanness composite（0=人味高, 100=问题多）
    # 先评分，参数层检查（第五层）直接消费评分结果
    scored = hs.score_article(text)
    findings = (
        check_structure(text, intent) +
        check_paragraphs(text) +
        check_sentences(text) +
        check_wording(text) +
        check_params(scored)
    )
    golden = find_golden_sentence_candidates(text)
    baseline = {
        "humanness": scored["composite_score"],
        "param_scores": {k: v for k, v in scored["param_scores"].items() if k in (
            "sentence_variance", "paragraph_rhythm", "adverb_density", "negative_emotion_floor",
            "broken_sentence_rate", "self_correction_rate", "word_temperature_bias")},
        "char_count": scored["char_count"],
    }

    report = {
        "baseline": baseline,
        "layers": {"structure": [], "paragraph": [], "sentence": [], "wording": [], "param": []},
        "golden_sentences": golden,
        "after": {},
    }
    # 按层归档（保留 impact 字段，去掉 layer 冗余键）
    for f in findings:
        report["layers"][f["layer"]].append({k: v for k, v in f.items() if k != "layer"})

    save_output_entity(_entity_stem(Path(markdown_path)), "revision", report)

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report, Path(markdown_path).stem)
    return report


def _print_report(report: dict, stem: str) -> None:
    total = sum(len(v) for v in report["layers"].values())
    print(f"RevisionReport（output/{stem}-revision.yaml）— 共 {total} 条")
    print(f"baseline humanness: {report['baseline'].get('humanness')}/100（0=人味高, 100=问题多）")
    if report["golden_sentences"]:
        print("金句候选：")
        for g in report["golden_sentences"]:
            print(f"  • {g}")
    else:
        print("金句候选：无（建议补 1-2 句可截图转发的句子）")
    for layer, name, arrow in [("param", "参数层", "="), ("structure", "结构层", ">>>"), ("paragraph", "段落层", ">>"), ("sentence", "句子层", ">"), ("wording", "措辞层", "")]:
        items = report["layers"].get(layer, [])
        if not items:
            continue
        print(f"{arrow} {name}（{len(items)}）")
        for f in items:
            print(f"   [{f['impact']}] {f['location']} — {f['issue']}")
            print(f"        改法：{f['fix']}")


def apply(markdown_path: str, dry_run: bool = False) -> None:
    path = Path(markdown_path)
    text = path.read_text(encoding="utf-8")
    new_text, log = apply_wording_fixes(text)

    if not log:
        print("措辞层无可自动修复项（空话/全角数字/重复标点/重复行）。")
        return

    print(f"将执行 {len(log)} 项措辞层修复：")
    for item in log:
        print(f"  • {item}")
    if dry_run:
        print("（dry-run，未写入）")
        return

    # 备份（回滚守卫）
    backup = output_entity_path(path.stem, "revision").with_name(f"{path.stem}-revision.orig.md")
    backup.write_text(text, encoding="utf-8")
    path.write_text(new_text, encoding="utf-8")
    print(f"已写入：{path}")
    print(f"备份：{backup}（可用 rollback 恢复）")
    print("下一步：python3 toolkit/revision.py recheck <file> 验证修改是否让文章变好。")


def recheck(markdown_path: str, as_json: bool = False) -> dict:
    path = Path(markdown_path)
    text = path.read_text(encoding="utf-8")
    stem = _entity_stem(path)

    rep_path = output_entity_path(stem, "revision")
    report = load_output_entity(stem, "revision")
    baseline = report.get("baseline") or {}

    scored = hs.score_article(text)
    after = {
        "humanness": scored["composite_score"],
        "param_scores": {k: v for k, v in scored["param_scores"].items() if k in (
            "sentence_variance", "paragraph_rhythm", "adverb_density", "negative_emotion_floor",
            "broken_sentence_rate", "self_correction_rate", "word_temperature_bias")},
        "char_count": scored["char_count"],
    }
    report["after"] = after
    save_output_entity(stem, "revision", report)

    before_h = baseline.get("humanness")
    delta = (after["humanness"] - before_h) if before_h is not None else None

    if as_json:
        print(json.dumps({"baseline": baseline, "after": after, "delta": delta}, ensure_ascii=False, indent=2))
    else:
        print(f"复检：baseline={before_h} → after={after['humanness']}（0=人味高, 100=问题多）")
        if delta is None:
            print("未找到 baseline，请先运行 analyze。")
        elif delta <= 2:
            print(f"✓ 未劣化（Δ{delta:+.2f}），修改通过。")
        elif delta <= 5:
            print(f"⚠ 轻微上升（Δ{delta:+.2f}），可接受；仍可继续优化。")
        else:
            print(f"✗ 明显恶化（Δ{delta:+.2f}），建议回滚：python3 toolkit/revision.py rollback <file>")
        if report.get("golden_sentences"):
            print(f"金句候选保留 {len(report['golden_sentences'])} 句。")
    return report


def rollback(markdown_path: str) -> None:
    path = Path(markdown_path)
    backup = output_entity_path(path.stem, "revision").with_name(f"{path.stem}-revision.orig.md")
    if not backup.exists():
        print("没有可恢复的备份（先运行 apply 才会生成）。")
        return
    path.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"已回滚：{path} ← {backup}")


def main():
    parser = argparse.ArgumentParser(prog="revision", description="WeWrite 四层修改工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_a = sub.add_parser("analyze", help="四层静态检查 → RevisionReport")
    p_a.add_argument("input", help="Markdown 文件路径")
    p_a.add_argument("--intent", help="IntentCard 文件路径（output/<slug>-intent.yaml，可选）")
    p_a.add_argument("--json", action="store_true", help="JSON 输出")

    p_ap = sub.add_parser("apply", help="自动执行措辞层机械修复（改前备份）")
    p_ap.add_argument("input", help="Markdown 文件路径")
    p_ap.add_argument("--dry-run", action="store_true", help="只预览不写入")

    p_r = sub.add_parser("recheck", help="改后复检（baseline vs after）")
    p_r.add_argument("input", help="Markdown 文件路径")
    p_r.add_argument("--json", action="store_true", help="JSON 输出")

    p_rb = sub.add_parser("rollback", help="恢复 apply 前的备份")
    p_rb.add_argument("input", help="Markdown 文件路径")

    args = parser.parse_args()
    try:
        if args.command == "analyze":
            analyze(args.input, intent_path=args.intent, as_json=args.json)
        elif args.command == "apply":
            apply(args.input, dry_run=args.dry_run)
        elif args.command == "recheck":
            recheck(args.input, as_json=args.json)
        elif args.command == "rollback":
            rollback(args.input)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()