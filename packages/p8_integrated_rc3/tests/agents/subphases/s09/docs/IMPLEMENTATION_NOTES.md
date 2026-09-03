# Implementation notes

## M01

The monitor is explicitly state-in/state-out. EWMA and two-sided CUSUM are transparent champion methods. No hidden process memory or network access exists.

## M02

The invariant monitor independently recomputes conservation identities from a closed snapshot. Accounting uncertainty produces a state inconsistency; it is not silently repaired.

## M03

The supervisor emits declarative modes. A partial fill is treated before generic halt logic because halting can preserve an unsafe temporary exposure.

## M04

The challenger contract uses `Literal[False]` for execution authority and requires identical input/scenario/constraint hashes before comparison.

## M05

Runtime adaptation is accepted only when it is monotonic in the conservative direction and inside promoted bounds.
