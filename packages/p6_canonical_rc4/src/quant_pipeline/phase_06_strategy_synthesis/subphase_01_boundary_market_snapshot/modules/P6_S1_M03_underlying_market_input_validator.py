"""P6.S1.M03 module wrapper."""

from ..runner_support import validate_underlyings

MODULE_ID = "P6.S1.M03"


def run(inputs, context):
    return validate_underlyings(inputs, context)
