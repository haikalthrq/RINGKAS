from __future__ import annotations

import pytest
from pydantic import SecretStr

from ringkas_worker.cloudflare_accounts import CloudflareAccountConfigurationError, CloudflareAccountPool


def test_canonical_pool_orders_accounts_and_advances_after_failure() -> None:
    pool = CloudflareAccountPool.from_values([("primary", "primary-token"), ("secondary", "secondary-token"), ("tertiary", "tertiary-token")])

    assert [account.account_id for account in pool.ordered_accounts()] == ["primary", "secondary", "tertiary"]
    pool.mark_failed(0)
    assert pool.active_index == 1
    assert [account.account_id for account in pool.ordered_accounts()] == ["secondary", "tertiary"]


def test_canonical_pool_reads_common_environment_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "primary")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "primary-token")
    monkeypatch.setenv("CLOUDFLARE_SECONDARY_ACCOUNT_ID", "secondary")
    monkeypatch.setenv("CLOUDFLARE_SECONDARY_API_TOKEN", "secondary-token")
    monkeypatch.setenv("CLOUDFLARE_TERTIARY_ACCOUNT_ID", "tertiary")
    monkeypatch.setenv("CLOUDFLARE_TERTIARY_API_TOKEN", "tertiary-token")

    pool = CloudflareAccountPool.from_environment()

    assert [account.account_id for account in pool.accounts] == ["primary", "secondary", "tertiary"]
    assert pool.accounts[1].api_token == SecretStr("secondary-token")


@pytest.mark.parametrize(
    "values",
    [
        [("primary", "token"), ("secondary", "")],
        [("primary", "token"), ("secondary", "token"), ("secondary", "other")],
        [("primary", "token"), ("bad account", "token")],
    ],
)
def test_incomplete_duplicate_or_unsafe_pool_is_rejected(values: list[tuple[str, str]]) -> None:
    with pytest.raises(CloudflareAccountConfigurationError):
        CloudflareAccountPool.from_values(values)
