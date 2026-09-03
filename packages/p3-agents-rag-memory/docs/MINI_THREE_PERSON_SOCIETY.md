# Mini three-person society

This is a real S5→S8 integration profile for a small laboratory society. It
uses the same personality candidate generator, consistency validation,
coverage controller, population representation, and social graph builder as
the canonical P3 pipeline.

Run it from the repository root:

```text
py -3 tools/run_mini_three_person_society.py
```

The profile is explicit in
`config/population/mini_three_person_profile.yaml`. It is deliberately marked
`laboratory_only`: the production population policy requires a larger
representative population. The mini profile is therefore useful for proving
end-to-end behavior, not for production promotion or statistical claims.

The run validates three unique people, a connected reciprocal social graph,
and the lineage/validation contracts. It uses a structured LLM fixture so the
test is deterministic; replacing the fixture provider with NVIDIA NIM is a
separate live-provider qualification step.
