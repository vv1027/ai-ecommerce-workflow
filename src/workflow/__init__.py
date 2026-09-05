"""
工作流模块 — 状态机 + 6个自动化触发点
"""
from .state_machine import StateMachine, ProductStateMachine
from .triggers import WorkflowTriggers

__all__ = ["StateMachine", "ProductStateMachine", "WorkflowTriggers"]
