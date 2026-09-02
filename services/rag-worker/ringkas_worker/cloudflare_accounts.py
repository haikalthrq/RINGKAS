from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

from pydantic import SecretStr


class CloudflareAccountConfigurationError(ValueError):
    """Safe configuration error for the shared Cloudflare account pool."""


@dataclass(frozen=True, slots=True)
class CloudflareAccount:
    account_id: str
    api_token: SecretStr
    index: int

    def __post_init__(self) -> None:
        if not self.account_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in self.account_id):
            raise CloudflareAccountConfigurationError("Cloudflare account ID is invalid")
        if not isinstance(self.api_token, SecretStr) or not self.api_token.get_secret_value().strip():
            raise CloudflareAccountConfigurationError("Cloudflare account token is required")
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 0 or self.index > 2:
            raise CloudflareAccountConfigurationError("Cloudflare account index is invalid")


class CloudflareAccountPool:
    """Canonical ordered Cloudflare account pool shared by all Python clients."""

    def __init__(self, accounts: Iterable[CloudflareAccount]) -> None:
        values = tuple(accounts)
        if not values or values[0].index != 0:
            raise CloudflareAccountConfigurationError("Cloudflare primary account is required")
        if tuple(account.index for account in values) != tuple(range(len(values))):
            raise CloudflareAccountConfigurationError("Cloudflare account indexes must be contiguous")
        ids = [account.account_id.casefold() for account in values]
        if len(ids) != len(set(ids)):
            raise CloudflareAccountConfigurationError("Cloudflare accounts must be unique")
        self._accounts = values
        self._active_index = 0

    @property
    def accounts(self) -> tuple[CloudflareAccount, ...]:
        return self._accounts

    @property
    def active_index(self) -> int:
        return self._active_index

    def ordered_accounts(self) -> tuple[CloudflareAccount, ...]:
        return self._accounts[self._active_index :]

    def mark_failed(self, account_index: int) -> None:
        if account_index >= self._active_index:
            self._active_index = min(account_index + 1, len(self._accounts))

    @classmethod
    def from_environment(cls) -> CloudflareAccountPool:
        primary_token = os.getenv("CLOUDFLARE_API_TOKEN") or os.getenv("CLOUDFLARE_WORKERS_AI_TOKEN", "")
        configured = (
            (os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), primary_token),
            (os.getenv("CLOUDFLARE_SECONDARY_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_SECONDARY_API_TOKEN", "")),
            (os.getenv("CLOUDFLARE_TERTIARY_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_TERTIARY_API_TOKEN", "")),
        )
        accounts: list[CloudflareAccount] = []
        for index, (account_id, token) in enumerate(configured):
            has_id, has_token = bool(account_id.strip()), bool(token.strip())
            if index == 0 and not (has_id and has_token):
                raise CloudflareAccountConfigurationError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required")
            if index > 0 and has_id != has_token:
                raise CloudflareAccountConfigurationError("Cloudflare optional account configuration is incomplete")
            if has_id and has_token:
                accounts.append(CloudflareAccount(account_id.strip(), SecretStr(token), index))
        return cls(accounts)

    @classmethod
    def from_values(cls, values: Iterable[tuple[str, str]]) -> CloudflareAccountPool:
        return cls(CloudflareAccount(account_id, SecretStr(token), index) for index, (account_id, token) in enumerate(values))
