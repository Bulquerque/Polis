"""P6.S3.M05 wrapper."""
from ..runner_support import family
MODULE_ID="P6.S3.M05"
def run(inputs,context,configuration):
 return family(inputs,context,configuration,"term",MODULE_ID,"term_structure_candidates")
