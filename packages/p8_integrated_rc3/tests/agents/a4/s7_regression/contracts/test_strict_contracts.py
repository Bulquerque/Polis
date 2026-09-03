import pytest
from pydantic import ValidationError

from quant_pipeline.phase_08_portfolio_control.foundation.context import ModuleExecutionContext


@pytest.mark.contract
def test_extra_fields_are_forbidden(context):
    data=context.model_dump(mode="python")
    data["unexpected"]="no"
    with pytest.raises(ValidationError):
        ModuleExecutionContext.model_validate(data)


@pytest.mark.contract
def test_json_schema_is_closed():
    schema=ModuleExecutionContext.model_json_schema()
    assert schema["additionalProperties"] is False
