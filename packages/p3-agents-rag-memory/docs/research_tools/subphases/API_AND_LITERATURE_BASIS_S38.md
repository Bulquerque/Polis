# API and literature basis — S38

The runtime is deliberately offline. SEC submissions and XBRL company facts are upstream ingestion references, not live backtest dependencies. XBRL facts must preserve taxonomy concepts, units, periods, filing versions and availability. Arelle may be used upstream for XBRL validation, but not as shared concurrent state inside P3. Scenario DCF and reverse DCF use explicit assumptions and return scenario values only.
