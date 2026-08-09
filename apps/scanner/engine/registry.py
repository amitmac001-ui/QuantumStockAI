"""
Legacy Strategy Registry

Deprecated.

DecisionEngine directly owns and executes all strategies.
This module is kept only for backward compatibility.
"""


class StrategyRegistry:

    @classmethod
    def register(cls, *args, **kwargs):
        pass

    @classmethod
    def clear(cls):
        pass

    @classmethod
    def all(cls):
        return []