
from __future__ import annotations
import json
import re
from pathlib import Path
import yaml

REQUIRED_ROOT_FILES = {'README.md', 'START_HERE.md', 'CHANGELOG.md'}

def yaml_load(path: Path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))

def all_yaml(root: Path):
    return [p for p in root.rglob('*.yaml') if '.git' not in p.parts]

def all_json(root: Path):
    return [p for p in root.rglob('*.json') if '.git' not in p.parts]

def module_sort_key(module_id: str):
    return tuple(int(x) for x in re.findall(r'\d+', module_id))
