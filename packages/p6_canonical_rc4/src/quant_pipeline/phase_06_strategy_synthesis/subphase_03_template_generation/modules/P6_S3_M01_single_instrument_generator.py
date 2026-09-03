"""P6.S3.M01 wrapper."""
from ..runner_support import family
MODULE_ID="P6.S3.M01"
def run(inputs,context,configuration):
 return family(inputs,context,configuration,"single",MODULE_ID,"single_instrument_candidates")
