"""Explicit population module registry; no reflection or import-time discovery."""

MODULE_HANDLER_PATHS: dict[str, str] = {
    "P3.S5.M01": "s5.PersonalityCandidateGenerator.execute",
    "P3.S5.M02": "s5.PersonalityCandidateConsistencyChecker.execute",
    "P3.S6.M01": "s6.PersonalityCoverageMetricCalculator.execute",
    "P3.S6.M02": "s6.CoverageDensityController.execute",
    "P3.S7.M01": "s7.FixedPopulationBuilder.execute",
    "P3.S7.M02": "s7.PopulationConsistencyValidator.execute",
    "P3.S8.M01": "s8.InitialSocialGraphBuilder.execute",
    "P3.S8.M02": "s8.RelationshipPriorValidator.execute",
}
