"""P6.S3.M03 wrapper."""
from ..runner_support import family
MODULE_ID="P6.S3.M03"
def run(inputs,context,configuration):
 return family(inputs,context,configuration,"volatility",MODULE_ID,"volatility_structure_candidates")
