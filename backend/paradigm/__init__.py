"""
NeuroViz 范式设计器模块
支持MI/P300/SSVEP等BCI实验范式
"""

from .controller import (
    ParadigmController,
    ParadigmConfig,
    TrialConfig,
    ParadigmType,
    TrialPhase,
    TrialState,
    create_mi_paradigm,
    create_p300_paradigm,
    create_ssvep_paradigm,
    create_neurofeedback_paradigm
)

from .api import router

__all__ = [
    "ParadigmController",
    "ParadigmConfig", 
    "TrialConfig",
    "ParadigmType",
    "TrialPhase",
    "TrialState",
    "create_mi_paradigm",
    "create_p300_paradigm",
    "create_ssvep_paradigm",
    "create_neurofeedback_paradigm",
    "router"
]
