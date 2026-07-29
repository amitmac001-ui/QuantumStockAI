from apps.companies.repositories.company_repository import CompanyRepository
from apps.core.services import BaseService
from apps.core.services import ServiceResult


class CompanyService(BaseService):

    @staticmethod
    def total_companies() -> int:
        return CompanyRepository.count()

    @staticmethod
    def get(symbol: str):

        company = CompanyRepository.by_symbol(symbol)

        if company is None:
            return ServiceResult.fail(
                message="Company not found",
            )

        return ServiceResult.ok(
            data=company,
        )

    @staticmethod
    def search(keyword: str):
        return CompanyRepository.search(keyword)

    @staticmethod
    def active():
        return CompanyRepository.active()
