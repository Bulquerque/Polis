from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def test_option_modules_ignore_non_option_p1_record():
    from quant_pipeline.phase_02_quality_pit.modules.P2_S4_M01_option_contract_parser import run_module as parse
    from quant_pipeline.phase_02_quality_pit.modules.P2_S4_M02_option_quote_cleaner import run_module as clean

    inputs = {
        "identifier_harmonized_bundle": {
            "records": [{"source_id": "b3-local", "source_category": "b3", "lineage_id": "lineage-b3"}]
        },
        "clean_calendar_panel": {"records": []},
        "source_quality_panel": {"records": []},
    }
    contracts = parse(inputs, {})["outputs"]["clean_option_contract_panel"]
    quotes = clean({**inputs, "clean_option_contract_panel": contracts}, {})["outputs"]["clean_option_quotes_panel"]
    assert contracts["records"] == []
    assert quotes["records"] == []
