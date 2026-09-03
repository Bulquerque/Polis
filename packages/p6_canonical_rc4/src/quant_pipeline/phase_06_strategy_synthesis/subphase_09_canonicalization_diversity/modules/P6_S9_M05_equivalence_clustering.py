"""P6.S9.M05 wrapper."""
from ..runner_support import cluster
MODULE_ID="P6.S9.M05"
def run(inputs,context,configuration): return cluster(inputs,configuration,context)
