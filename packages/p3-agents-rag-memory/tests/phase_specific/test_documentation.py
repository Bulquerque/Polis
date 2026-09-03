
import re
from pathlib import Path
from .helpers import REQUIRED_ROOT_FILES

def test_docs_start_here_exists(plan_root):
    assert (plan_root/'docs'/'README.md').exists()
    assert (plan_root/'docs'/'00_START_HERE'/'README.md').exists()
    assert (plan_root/'docs'/'00_START_HERE'/'READING_PATHS.md').exists()
    assert (plan_root/'docs'/'00_START_HERE'/'GLOSSARY.md').exists()

def test_source_of_truth_names_canonical_contract_files(plan_root):
    text=(plan_root/'docs'/'02_CONTRACTS'/'SOURCE_OF_TRUTH.md').read_text(encoding='utf-8')
    for name in ['INPUT_CONTRACTS.yaml','OUTPUT_CONTRACTS.yaml','MODULE_IO_MATRIX.yaml','INTERNAL_ARTIFACT_REGISTRY.yaml']:
        assert name in text

def test_internal_markdown_links_resolve(plan_root):
    broken=[]
    pattern=re.compile(r'\[[^\]]*\]\(([^)]+)\)')
    for p in plan_root.rglob('*.md'):
        if 'archive' in p.parts:
            continue
        text=p.read_text(encoding='utf-8')
        for target in pattern.findall(text):
            target=target.split('#',1)[0]
            if not target or '://' in target or target.startswith('mailto:'):
                continue
            resolved=(p.parent/target).resolve()
            try: resolved.relative_to(plan_root.resolve())
            except ValueError: continue
            if not resolved.exists(): broken.append((str(p.relative_to(plan_root)),target))
    assert not broken

def test_root_entrypoints_are_substantive(plan_root):
    too_short=[]
    for name in REQUIRED_ROOT_FILES:
        p=plan_root/name
        if len(p.read_text(encoding='utf-8').strip())<180: too_short.append(name)
    assert not too_short
