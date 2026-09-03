"""P6.S3.M02 wrapper."""
from ..runner_support import family
MODULE_ID="P6.S3.M02"
def run(inputs,context,configuration):
 return family(inputs,context,configuration,"vertical",MODULE_ID,"vertical_candidates")
