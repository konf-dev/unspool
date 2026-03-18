import os

import pytest

from .admin import AdminClient
from .client import EvalClient


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--api-url",
        default=os.getenv("API_URL", "https://api.unspool.life"),
        help="Base URL for the API",
    )


@pytest.fixture(scope="session")
def api_url(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--api-url")


@pytest.fixture(scope="session")
def eval_api_key() -> str:
    key = os.getenv("EVAL_API_KEY")
    if not key:
        pytest.skip("EVAL_API_KEY not set")
    return key


@pytest.fixture(scope="session")
def admin_api_key() -> str:
    key = os.getenv("ADMIN_API_KEY")
    if not key:
        pytest.skip("ADMIN_API_KEY not set")
    return key


@pytest.fixture(scope="session")
def client(api_url: str, eval_api_key: str) -> EvalClient:
    return EvalClient(base_url=api_url, auth_token=f"eval:{eval_api_key}")


@pytest.fixture(scope="session")
def admin(api_url: str, admin_api_key: str) -> AdminClient:
    return AdminClient(base_url=api_url, admin_key=admin_api_key)


EVAL_USER_ID = "b8a2e17e-ff55-485f-ad6c-29055a607b33"
