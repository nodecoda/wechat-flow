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
