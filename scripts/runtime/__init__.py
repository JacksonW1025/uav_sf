"""Reusable V8 infrastructure primitives; no experiment runner is active."""

from scripts.runtime.isolation import IsolationAllocation, allocate_isolation

__all__ = ["IsolationAllocation", "allocate_isolation"]
