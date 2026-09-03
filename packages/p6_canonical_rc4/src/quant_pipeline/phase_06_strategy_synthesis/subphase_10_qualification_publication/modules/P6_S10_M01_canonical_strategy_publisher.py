"""P6.S10.M01 canonical strategy publisher."""

from ..runner_support import publish_canonical_outputs

MODULE_ID = "P6.S10.M01"


def run(inputs, context, configuration):
    return publish_canonical_outputs(dict(inputs), context, configuration)
