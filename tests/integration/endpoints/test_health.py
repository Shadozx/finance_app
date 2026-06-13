from fastapi import status
from httpx import AsyncClient

API_HEALTH = "/api/v1/health"
API_HEALTH_READY = "/api/v1/health/ready"


class TestHealth:
    async def test_health_success(
            self,
            client: AsyncClient,
    ):
        response = await client.get(API_HEALTH)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}


class TestReady:
    async def test_ready_success(
            self,
            client: AsyncClient,
    ):
        response = await client.get(API_HEALTH_READY)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ready"}
