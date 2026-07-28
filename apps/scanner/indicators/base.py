from abc import ABC
from abc import abstractmethod


class BaseIndicator(ABC):

    name = ""

    version = "1.0.0"

    @abstractmethod
    def calculate(self, candles):

        raise NotImplementedError
