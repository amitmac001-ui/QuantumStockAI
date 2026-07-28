from abc import ABC
from abc import abstractmethod

from .result import ScanContext


class BaseStrategy(ABC):

    name = ""

    version = "1.0.0"

    category = ""

    priority = 100

    @abstractmethod
    def scan(
        self,
        context: ScanContext,
    ):
        raise NotImplementedError

    def execute(
        self,
        context: ScanContext,
    ):

        return self.scan(context)
