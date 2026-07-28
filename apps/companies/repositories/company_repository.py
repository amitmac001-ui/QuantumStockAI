from apps.companies.models import Company
from apps.core.repositories.base import BaseRepository


class CompanyRepository(BaseRepository):

    model = Company

    @classmethod
    def by_symbol(cls, symbol):
        return cls.model.objects.filter(
            symbol=symbol,
        ).first()

    @classmethod
    def active(cls):
        return cls.model.objects.filter(
            is_active=True,
        )

    @classmethod
    def search(cls, keyword):
        return cls.model.objects.filter(
            company_name__icontains=keyword,
        )
