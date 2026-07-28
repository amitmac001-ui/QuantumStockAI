from importlib import import_module
from pkgutil import iter_modules

from apps.scanner.engine.registry import StrategyRegistry
import apps.scanner.strategies


def discover():

    package = apps.scanner.strategies

    for _, module_name, _ in iter_modules(
        package.__path__
    ):

        module = import_module(
            f"{package.__name__}.{module_name}"
        )

        for obj in module.__dict__.values():

            if (
                isinstance(obj, type)
                and obj.__name__.endswith("Strategy")
                and obj.__name__ != "BaseStrategy"
            ):

                StrategyRegistry.register(
                    obj()
                )
