# Code quality policy

- Productive files target <= 350 physical lines.
- Functions target <= 60 physical lines.
- Closed Pydantic models: strict, frozen and extra forbidden.
- No broad catch in domain code.
- No hidden global mutable state.
- No network or broker dependency.
- No default PASS or synthetic timestamp/ID from missing inputs.
- No challenger execution authority.
- Missing data never becomes zero or normality.
