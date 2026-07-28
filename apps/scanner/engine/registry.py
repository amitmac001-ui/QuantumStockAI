class StrategyRegistry:

    _strategies = {}

    @classmethod
    def register(cls, strategy):

        cls._strategies[strategy.name] = strategy

    @classmethod
    def get(cls, name):

        return cls._strategies.get(name)

    @classmethod
    def all(cls):

        return tuple(
            sorted(
                cls._strategies.values(),
                key=lambda s: s.priority,
            )
        )

    @classmethod
    def clear(cls):

        cls._strategies.clear()

    @classmethod
    def count(cls):

        return len(cls._strategies)
