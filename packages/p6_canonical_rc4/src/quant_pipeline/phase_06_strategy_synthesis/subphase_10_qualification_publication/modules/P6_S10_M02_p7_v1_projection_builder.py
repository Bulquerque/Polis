"""P6.S10.M02 temporary P7 V1 projection builder."""

from ..runner_support import publish_legacy_projection

MODULE_ID = "P6.S10.M02"


def run(inputs, context, configuration):
    return publish_legacy_projection(dict(inputs), context, configuration)
