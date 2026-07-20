# -*- coding: utf-8 -*-
"""Decision Sandbox - multi-path comparison system for CampusPal.

Orchestrates a 4-phase workflow:
    1. DISCOVERY     - collect universal user profile
    2. PATH_PROBE    - path-specific questions
    3. PARALLEL_SIM  - run planning agents in parallel
    4. PROJECTION    - compare results via ProjectionAgent

Exports:
    - DecisionSandbox: orchestrator class
    - ProjectionAgent: standalone comparison agent
    - SandboxSession: state model
    - All schemas for API integration
"""

from sandbox.orchestrator import DecisionSandbox
from sandbox.projection import ProjectionAgent
from sandbox.state import SandboxSession, SandboxPhase, SANDBOX_PATHS

__all__ = [
    "DecisionSandbox",
    "ProjectionAgent",
    "SandboxSession",
    "SandboxPhase",
    "SANDBOX_PATHS",
]
