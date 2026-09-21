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

# 每个 gate 实际读取的输入面（相对域根），随 harness 结果一起输出，供读者判断
# "本次到底查了什么" —— 否则 `ok: true` 与"一个 gate 都没跑"在输出上不可区分。
#
# 约定：`*` = 该层非递归 glob；`**` = 递归；单个 DOMAIN.yaml = 只读清单字段，不读内容面。
# ⚠️ **新增或修改 gate 时必须同步本表**，否则本表就从"自证"退化为"自述"。
GATE_SURFACES: dict[str, tuple[str, ...]] = {
    "T0": ("DOMAIN.yaml",),
    "T1": ("DOMAIN.yaml",),
    "T2": ("DOMAIN.yaml",),
    "T4": ("_control/skills/*.yaml", "_control/workflows/*.yaml"),
    "T7": ("DOMAIN.yaml",),
    "T8": ("<domain-root>/**",),
}
