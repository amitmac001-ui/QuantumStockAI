from django.db.models import QuerySet

from apps.companies.models import Company
from apps.core.repositories.base import BaseRepository


class CompanyRepository(BaseRepository):

    model = Company

    @classmethod
    def count(cls) -> int:
        return cls.model.objects.count()

    @classmethod
    def active(cls) -> QuerySet:
        return (
            cls.model.objects
            .filter(is_active=True)
        )

    @classmethod
    def by_symbol(cls, symbol: str):
        return (
            cls.model.objects
            .filter(symbol=symbol.upper())
            .first()
        )

    @classmethod
    def search(
        cls,
        keyword: str,
    ) -> QuerySet:
        return (
            cls.model.objects
            .filter(company_name__icontains=keyword)
            .order_by("company_name")
        )
