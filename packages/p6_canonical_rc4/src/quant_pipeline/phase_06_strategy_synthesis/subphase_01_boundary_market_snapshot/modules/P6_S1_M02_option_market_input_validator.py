"""P6.S1.M02 module wrapper."""

from ..runner_support import validate_options

MODULE_ID = "P6.S1.M02"


def run(inputs, context):
    return validate_options(inputs, context)
