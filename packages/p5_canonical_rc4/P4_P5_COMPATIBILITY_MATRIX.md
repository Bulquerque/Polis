# P4→P5 compatibility

| P4 input | P5 handling | Failure policy |
|---|---|---|
| consumer view manifest/bundle | recursive contract and hash validation | reject mismatch |
| feature filters and metadata | authorized materialization only | required unmatched filter rejected |
| decision/availability clocks | point-in-time validation | future or missing required availability rejected |
| quality and masks | preserved in feature bundle | no permissive inference |
| P4 V14.9 references | locked by checksums | changed reference rejected |
