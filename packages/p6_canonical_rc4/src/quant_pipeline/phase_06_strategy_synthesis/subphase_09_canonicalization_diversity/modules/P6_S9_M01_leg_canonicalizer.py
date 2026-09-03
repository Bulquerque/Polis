"""P6.S9.M01 wrapper."""
from ..runner_support import canonicalize
MODULE_ID="P6.S9.M01"
def run(inputs,context,configuration): return canonicalize(inputs,configuration,context)
