from app.core.openapi import API_DESCRIPTION
from app.main import app


class TestOpenapi:
    def test_openapi_contains_client_requirements(self):
        assert app.openapi()["info"]["description"] == API_DESCRIPTION
