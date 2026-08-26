import copy
from pathlib import Path

import yaml


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
        Path.home() / ".config" / "wewrite" / "config.yaml",
    ]


def find_config_path(skill_root: Path | str | None = None) -> Path | None:
    for path in config_search_paths(skill_root):
        if path.exists():
            return path
    return None


def load_yaml_file(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or default


def load_config(skill_root: Path | str | None = None) -> dict:
    path = find_config_path(skill_root)
    if path is not None:
        return load_yaml_file(path, {})
    return {}


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
    return normalize_history(load_yaml_file(path, []))


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
