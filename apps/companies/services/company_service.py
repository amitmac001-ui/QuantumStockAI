from apps.companies.repositories import CompanyRepository
from apps.core.services import BaseService
from apps.core.services import ServiceResult


class CompanyService(BaseService):

    def handle(
        self,
        symbol: str,
    ):

        company = CompanyRepository.by_symbol(symbol)

        if company is None:
            return ServiceResult.fail(
                message="Company not found",
            )

        return ServiceResult.ok(
            data=company,
        )
