"""P6.S3.M04 wrapper."""
from ..runner_support import family
MODULE_ID="P6.S3.M04"
def run(inputs,context,configuration):
 return family(inputs,context,configuration,"skew",MODULE_ID,"skew_asymmetric_candidates")
