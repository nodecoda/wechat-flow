#!/usr/bin/env python3
"""
Edit-anchor tooling for WeWrite (Phase A).

编辑锚点是写作后留给用户填入个人内容的标记位（人机协作节点）。
结构化语法（Markdown 容器）：

    :::anchor experience
    在这里加一句你自己的话：写一段真实的个人经历或感受（1-2 句即可）。
    :::

类型：experience（经历）/ opinion（判断）/ story（细节）/ data（数据）

Usage:
    python3 toolkit/anchor.py generate article.md [--count 2] [--force]
    python3 toolkit/anchor.py check   article.md [--json]

generate：在文章约 1/3、2/3 处插入锚点块，并把锚点清单写入
          output/<stem>-anchors.yaml。幂等：已有锚点则跳过（--force 重新生成）。
check   ：扫描未填写的锚点块并报告；全部填写返回 exit 0，否则 exit 1（可作发布守卫）。
"""

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from wewrite_common import load_output_entity, output_entity_path, save_output_entity

ANCHOR_TYPES = ("experience", "opinion", "story", "data")

ANCHOR_PROMPTS = {
    "experience": "在这里加一句你自己的话：写一段真实的个人经历或感受（1-2 句即可）。",
    "opinion": "在这里加一句你自己的话：给出你的明确判断或立场。",
    "story": "在这里加一句你自己的话：补一个真实细节或场景。",
    "data": "在这里加一句你自己的话：补一个你知道的真实数据或案例。",
}

ANCHOR_RE = re.compile(r":::anchor\s+(\w+)\n(.*?)\n:::", re.DOTALL)


def _ensure_utf8_stdio():
    """Windows GBK 控制台无法打印 ✓/emoji，强制 stdout/stderr 走 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


_ensure_utf8_stdio()

DEFAULT_COUNT = 2


def _block(atype: str, prompt: str) -> str:
    return f":::anchor {atype}\n{prompt}\n:::"


def _insert_blocks(blocks: list[str], count: int) -> tuple[list[str], list[dict]]:
    """Insert anchor blocks after 1/(count+1), 2/(count+1), ... of the paragraphs.

    Skips the first block when it is the H1 title. Returns (new blocks, records).
    """
    start = 1 if len(blocks) > 1 and blocks[0].lstrip().startswith("#") else 0
    span = max(len(blocks) - start, 1)
    idxs = sorted({start + (span * k) // (count + 1) for k in range(1, count + 1)})
    idxs = [i for i in idxs if i < len(blocks)]
    records = []
    new_blocks = list(blocks)
    for offset, i in enumerate(idxs):
        atype = ANCHOR_TYPES[offset % len(ANCHOR_TYPES)]
        prompt = ANCHOR_PROMPTS[atype]
        records.append({
            "id": f"a{offset + 1}",
            "type": atype,
            "prompt": prompt,
            "location": f"段落 {i + 1}",
            "status": "unfilled",
        })
        new_blocks.insert(i + 1 + offset, _block(atype, prompt))
    return new_blocks, records


def generate_anchors(markdown_path: str, count: int = DEFAULT_COUNT, force: bool = False) -> Path:
    """Insert edit anchors into a Markdown article (idempotent)."""
    path = Path(markdown_path)
    text = path.read_text(encoding="utf-8")

    if ANCHOR_RE.search(text):
        if not force:
            print(f"已存在编辑锚点，跳过（--force 重新生成）：{path}")
            return path
        text = ANCHOR_RE.sub("", text)

    blocks = text.split("\n\n")
    new_blocks, records = _insert_blocks(blocks, count)
    path.write_text("\n\n".join(new_blocks), encoding="utf-8")

    record_path = save_output_entity(path.stem, "anchors", {"anchors": records})
    print(f"已插入 {len(records)} 个编辑锚点：{path}")
    for r in records:
        print(f"  {r['id']} [{r['type']}] {r['location']}")
    print(f"锚点清单：{record_path}")
    return path


def _line_number(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def check_anchors(markdown_path: str, as_json: bool = False) -> bool:
    """Scan for unfilled anchors; returns True when none remain (usable as a publish guard)."""
    path = Path(markdown_path)
    text = path.read_text(encoding="utf-8")

    unfilled = []
    for m in ANCHOR_RE.finditer(text):
        unfilled.append({
            "line": _line_number(text, m.start()),
            "type": m.group(1).strip().lower(),
            "prompt": m.group(2).strip(),
        })

    total = None
    record_path = output_entity_path(path.stem, "anchors")
    if record_path.exists():
        record = load_output_entity(path.stem, "anchors")
        total = len(record.get("anchors", []))
    remaining = len(unfilled)
    filled = (total - remaining) if total is not None else None

    if as_json:
        print(json.dumps(
            {"total": total, "remaining": remaining, "filled": filled, "unfilled": unfilled},
            ensure_ascii=False, indent=2,
        ))
    else:
        if total is not None:
            print(f"编辑锚点：total={total} filled={filled} remaining={remaining}")
        else:
            print(f"编辑锚点：remaining={remaining}（未找到锚点清单文件，无法计算 total）")
        for u in unfilled:
            print(f"  x line {u['line']:4d} [{u['type']}] {u['prompt']}")
        if remaining == 0:
            print("✓ 所有编辑锚点均已填写（或文章不含锚点）。")

    return remaining == 0


def main():
    parser = argparse.ArgumentParser(prog="anchor", description="WeWrite 编辑锚点工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate", help="在文章中插入编辑锚点（幂等）")
    p_gen.add_argument("input", help="Markdown 文件路径")
    p_gen.add_argument("--count", type=int, default=DEFAULT_COUNT, help=f"锚点数量（默认 {DEFAULT_COUNT}）")
    p_gen.add_argument("--force", action="store_true", help="先移除已有锚点再重新生成")

    p_chk = sub.add_parser("check", help="扫描未填写的编辑锚点")
    p_chk.add_argument("input", help="Markdown 文件路径")
    p_chk.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()
    try:
        if args.command == "generate":
            generate_anchors(args.input, count=args.count, force=args.force)
        else:
            ok = check_anchors(args.input, as_json=args.json)
            sys.exit(0 if ok else 1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()