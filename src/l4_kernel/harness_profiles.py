"""Built-in deterministic Phase 0 harness profiles."""

GATES = ("T0", "T1", "T2", "T4", "T7")

PROFILE_GATES = {
    "constitutional": GATES,
    "private-core": GATES,
    "operational": GATES,
    "library": ("T0", "T1", "T2", "T7"),
    "federation": ("T0", "T1", "T2", "T7"),
    "projection": ("T0", "T1", "T2", "T7"),
}
