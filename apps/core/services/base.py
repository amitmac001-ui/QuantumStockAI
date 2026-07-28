from django.db import transaction


class BaseService:

    @classmethod
    @transaction.atomic
    def execute(cls, *args, **kwargs):
        service = cls()
        return service.handle(*args, **kwargs)

    def handle(self, *args, **kwargs):
        raise NotImplementedError(
            f"{self.__class__.__name__}.handle() must be implemented."
        )
