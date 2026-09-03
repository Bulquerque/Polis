"""Explicit module registry for P3.S8."""
from .builder import InitialSocialGraphBuilder
from .validator import RelationshipPriorValidator

MODULE_HANDLERS = {
    "P3.S8.M01": InitialSocialGraphBuilder,
    "P3.S8.M02": RelationshipPriorValidator,
}
