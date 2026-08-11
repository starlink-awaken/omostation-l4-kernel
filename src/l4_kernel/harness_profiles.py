"""Built-in deterministic Phase 0 harness profiles."""

GATES = ("T0", "T1", "T2", "T4", "T7", "T8")

PHASE0_GATES = ("T0", "T1", "T2", "T4", "T7")

PROFILE_GATES = {
    "constitutional": PHASE0_GATES,
    "private-core": PHASE0_GATES,
    "operational": PHASE0_GATES,
    "library": ("T0", "T1", "T2", "T7"),
    "federation": ("T0", "T1", "T2", "T7"),
    "projection": ("T0", "T1", "T2", "T7"),
}
