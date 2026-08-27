import copy
import re
import sys
from pathlib import Path

import yaml


def _ensure_utf8_stdio():
    """Windows GBK 控制台无法打印中文/emoji，强制 stdout/stderr 走 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

ENTITY_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")


def entity_stem(markdown_path) -> str:
    """实体 key：去日期前缀的 slug（与 intent/facts 命名对齐）。"""
    stem = Path(markdown_path).stem
    return ENTITY_STEM_RE.sub("", stem)


def ensure_skill_root() -> Path:
    """Return the skill root and guarantee it is importable.

    ncoda_common.py always sits at the skill root: the repo root in the
    source layout (scripts/, toolkit/) and ``dist/openclaw/`` in the built
    layout. Scripts call this as the single source of truth for the root and
    for the sys.path bootstrap instead of repeating per-file boilerplate.
    """
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def _skill_root_from(value: Path | str | None) -> Path:
    if value is None:
        return Path(__file__).resolve().parent
    return Path(value).resolve()


def config_search_paths(skill_root: Path | str | None = None) -> list[Path]:
    root = _skill_root_from(skill_root)
    return [
        Path.cwd() / "config.yaml",
        root / "config.yaml",
        root / "toolkit" / "config.yaml",
        Path.home() / ".config" / "ncoda" / "config.yaml",
    ]



def find_config_path(skill_root: Path | str | None = None) -> Path | None:
    for path in config_search_paths(skill_root):
        if path.exists():
            return path
    return None


def style_search_paths(skill_root: Path | str | None = None) -> list[Path]:
    """style.yaml search paths, local (cwd) first — mirrors config layering."""
    root = _skill_root_from(skill_root)
    return [
        Path.cwd() / "style.yaml",
        root / "style.yaml",
        Path.home() / ".config" / "ncoda" / "style.yaml",
    ]


def find_style_path(skill_root: Path | str | None = None) -> Path | None:
    """Highest-priority existing style.yaml (local wins)."""
    for path in style_search_paths(skill_root):
        if path.exists():
            return path
    return None


def load_style(skill_root: Path | str | None = None) -> dict:
    """Load style.yaml with the same local-first merge semantics as config."""
    merged: dict = {}
    for path in reversed(style_search_paths(skill_root)):
        raw = load_yaml_file(path, None)
        if isinstance(raw, dict):
            merged = deep_merge(merged, raw)
    return merged


# --- WeChat multi-account helpers ---

def list_wechat_accounts(config: dict) -> list[dict]:
    """Normalize ``wechat.accounts`` into a list of dicts with a ``name`` key.

    Accounts missing a name get a generated ``account-N`` label.
    """
    wechat = config.get("wechat", {})
    if not isinstance(wechat, dict):
        return []
    accounts = wechat.get("accounts", [])
    if not isinstance(accounts, list):
        return []
    out: list[dict] = []
    for idx, acc in enumerate(accounts, start=1):
        if not isinstance(acc, dict):
            continue
        item = dict(acc)
        if not (item.get("appid") or item.get("name")):
            continue
        item.setdefault("name", f"account-{idx}")
        out.append(item)
    return out


def wechat_account_names(config: dict) -> list[str]:
    """Configured account names in order."""
    return [acc.get("name", "") for acc in list_wechat_accounts(config) if acc.get("name")]


def get_wechat_account(config: dict, name: str | None = None) -> dict | None:
    """Resolve a WeChat account by name; ``None`` resolves the default.

    Resolution order for ``name=None``:
      1. ``wechat.default`` account (must be complete)
      2. first complete account in ``wechat.accounts``
      3. legacy ``wechat.appid``/``wechat.secret`` block (named "default")

    A named lookup never silently falls back: unknown/incomplete name → None.
    Returns a dict with at least ``name``/``appid``/``secret``, or None.
    """
    accounts = list_wechat_accounts(config)
    wechat = config.get("wechat", {})
    if not isinstance(wechat, dict):
        wechat = {}

    if name:
        for acc in accounts:
            if acc.get("name") == name:
                if acc.get("appid") and acc.get("secret"):
                    return acc
                return None  # named but incomplete → no silent fallback
        return None  # unknown name

    default_name = wechat.get("default")
    if default_name:
        for acc in accounts:
            if acc.get("name") == default_name:
                if acc.get("appid") and acc.get("secret"):
                    return acc
                return None  # default points to an incomplete account → surface it
    for acc in accounts:
        if acc.get("appid") and acc.get("secret"):
            return acc
    if wechat.get("appid") and wechat.get("secret"):
        return {
            "name": "default",
            "appid": wechat["appid"],
            "secret": wechat["secret"],
            "author": wechat.get("author", ""),
        }
    return None


def load_yaml_file(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or default


def deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base, returning a new dict.

    Nested dicts merge key-by-key; lists and scalars from overlay replace base.
    Used for config layering: low-priority (global) first, local overrides win.
    """
    out = dict(base)
    for key, value in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(skill_root: Path | str | None = None) -> dict:
    """Load config with local-first layering.

    Search order (highest priority last in the merge loop, so it wins):
      ~/.config/ncoda/config.yaml  →  {skill_root}/toolkit/config.yaml
      → {skill_root}/config.yaml  →  {cwd}/config.yaml

    Multiple files are deep-merged, so a project-local ``config.yaml`` may
    contain only the sections it wants to override (e.g. ``wechat:``).
    """
    merged: dict = {}
    for path in reversed(config_search_paths(skill_root)):
        raw = load_yaml_file(path, None)
        if isinstance(raw, dict):
            merged = deep_merge(merged, raw)
    return merged


def history_path(skill_root: Path | str | None = None) -> Path:
    return _skill_root_from(skill_root) / "history.yaml"


def normalize_history(raw) -> list[dict]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]

    if isinstance(raw, dict):
        articles = raw.get("articles", [])
        if isinstance(articles, list):
            return [item for item in articles if isinstance(item, dict)]

    return []


def load_history(skill_root: Path | str | None = None) -> list[dict]:
    path = history_path(skill_root)
    if not path.exists():
        return []
    try:
        raw = load_yaml_file(path, [])
    except yaml.YAMLError:
        # 历史数据文件损坏（如旧版写入缺陷）时降级为空，不阻断诊断/去重流程
        return []
    return normalize_history(raw)


def save_history(articles: list[dict], skill_root: Path | str | None = None) -> Path:
    path = history_path(skill_root)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(list(articles), f, allow_unicode=True, default_flow_style=False)
    return path


def has_image_config(config: dict) -> bool:
    image_cfg = config.get("image", {})
    if not isinstance(image_cfg, dict):
        return False

    if image_cfg.get("api_key"):
        return True

    providers = image_cfg.get("providers")
    if isinstance(providers, list):
        for entry in providers:
            if isinstance(entry, dict) and entry.get("provider") and entry.get("api_key"):
                return True

    return False

# --- Writing-domain entities (Phase A: data contracts) ---
# Entities are stored under output/<stem>-<kind>.yaml, e.g.
#   2026-08-26-my-post-intent.yaml  /  -facts.yaml / -anchors.yaml / -revision.yaml

ENTITY_KINDS = ("intent", "facts", "anchors", "revision")

ENTITY_DEFAULTS = {
    "intent": {
        "topic": "",
        "thesis": "",
        "angle": "",  # 反转 / 升维 / 预测 / 筛选
        "thesis_candidates": [],  # 候选立意句（Agent 生成，人终审后 thesis=选中项）
        "info_gap": {"from": "", "to": ""},
        "evidence": [],  # [{claim, source, url}]
        "boundary": "",
        "title_candidates": [],
        "status": "generated",  # generated -> user_confirmed -> locked
    },
    "facts": {
        "items": [],  # [{claim, source_url, source_name, extracted_at, status}]
        "rules": [
            "写作引用必须命中 FactSheet 条目；命中 rejected 的条目不得引用",
            "数字/日期/人名三类信息强制溯源",
        ],
    },
    "anchors": {"anchors": []},  # [{id, type, prompt, location, status}]
    "revision": {
        "baseline": {},  # {humanness, banned, ...} 修改前
        "layers": {"structure": [], "paragraph": [], "sentence": [], "wording": []},
        "golden_sentences": [],
        "after": {},  # 修改后复检
    },
}


def entity_defaults(kind: str) -> dict:
    if kind not in ENTITY_DEFAULTS:
        raise ValueError(f"Unknown entity kind: {kind} (expected one of {', '.join(ENTITY_KINDS)})")
    return copy.deepcopy(ENTITY_DEFAULTS[kind])


def output_dir(skill_root: Path | str | None = None) -> Path:
    return _skill_root_from(skill_root) / "output"


def output_entity_path(stem: str, kind: str, skill_root: Path | str | None = None) -> Path:
    if kind not in ENTITY_KINDS:
        raise ValueError(f"Unknown entity kind: {kind} (expected one of {', '.join(ENTITY_KINDS)})")
    return output_dir(skill_root) / f"{stem}-{kind}.yaml"


def load_output_entity(stem: str, kind: str, skill_root: Path | str | None = None) -> dict:
    return load_yaml_file(output_entity_path(stem, kind, skill_root), entity_defaults(kind))


def save_output_entity(stem: str, kind: str, data: dict, skill_root: Path | str | None = None) -> Path:
    path = output_entity_path(stem, kind, skill_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    return path
