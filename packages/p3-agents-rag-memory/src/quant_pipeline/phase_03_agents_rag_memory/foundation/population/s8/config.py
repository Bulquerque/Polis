"""Configuration loader for P3.S8."""
from pathlib import Path
import yaml
from .models import SocialGraphConfig


def load_social_graph_config(path: str | Path) -> SocialGraphConfig:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return SocialGraphConfig.model_validate(value)
