from abc import ABC, abstractmethod
from typing import Any


class PmsApiError(Exception):
    def __init__(self, status_code: int, message: str, response_body: Any = None):
        self.status_code = status_code
        self.message = message
        self.response_body = response_body
        super().__init__(message)


class PmsClient(ABC):
    @abstractmethod
    async def test_connection(self) -> dict[str, Any]:
        pass

    @abstractmethod
    async def list_patients(self, limit: int = 50) -> Any:
        pass

    @abstractmethod
    async def get_patient(self, external_patient_id: str) -> Any:
        pass

    @abstractmethod
    async def list_appointments(
        self,
        date_start: str | None = None,
        date_end: str | None = None,
        limit: int = 50,
    ) -> Any:
        pass

    @abstractmethod
    async def list_providers(self) -> Any:
        pass