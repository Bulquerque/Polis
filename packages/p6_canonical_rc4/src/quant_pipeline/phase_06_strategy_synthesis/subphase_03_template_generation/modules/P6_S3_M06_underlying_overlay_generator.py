"""P6.S3.M06 wrapper."""
from ..runner_support import family
MODULE_ID="P6.S3.M06"
def run(inputs,context,configuration):
 return family(inputs,context,configuration,"overlay",MODULE_ID,"underlying_overlay_candidates")
