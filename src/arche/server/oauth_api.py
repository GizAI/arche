"""OAuth API client for Anthropic API.

Provides access to usage, profile, and other OAuth-protected endpoints.
Uses credentials from ~/.claude/.credentials.json.
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import logging

import requests

logger = logging.getLogger(__name__)


# Cache settings
_CACHE_TTL = 60  # 1 minute cache


@dataclass
class UsageInfo:
    """API usage information."""
    daily_spend_usd: float
    monthly_spend_usd: float
    daily_limit_usd: float | None
    monthly_limit_usd: float | None
    rate_limit_tier: str | None
    # 5-hour rolling window
    rolling_window_seconds: int
    rolling_window_tokens: int
    rolling_window_limit: int | None
    utilization_percent: float

    def to_dict(self) -> dict:
        return {
            "daily_spend_usd": self.daily_spend_usd,
            "monthly_spend_usd": self.monthly_spend_usd,
            "daily_limit_usd": self.daily_limit_usd,
            "monthly_limit_usd": self.monthly_limit_usd,
            "rate_limit_tier": self.rate_limit_tier,
            "rolling_window_seconds": self.rolling_window_seconds,
            "rolling_window_tokens": self.rolling_window_tokens,
            "rolling_window_limit": self.rolling_window_limit,
            "utilization_percent": self.utilization_percent,
        }


@dataclass
class ProfileInfo:
    """User profile information."""
    user_id: str
    email: str
    name: str | None
    organization_id: str | None
    organization_name: str | None

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "name": self.name,
            "organization_id": self.organization_id,
            "organization_name": self.organization_name,
        }


class OAuthAPIClient:
    """Client for OAuth-authenticated Anthropic API requests."""

    def __init__(self, credentials_path: Path | None = None):
        self.credentials_path = credentials_path or (Path.home() / ".claude" / ".credentials.json")
        self._token: str | None = None
        self._token_expiry: float = 0
        self._usage_cache: UsageInfo | None = None
        self._usage_cache_time: float = 0
        self._profile_cache: ProfileInfo | None = None
        self._profile_cache_time: float = 0

    def _load_credentials(self) -> dict | None:
        """Load OAuth credentials from file."""
        if not self.credentials_path.exists():
            logger.warning(f"Credentials file not found: {self.credentials_path}")
            return None

        try:
            with open(self.credentials_path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load credentials: {e}")
            return None

    def _get_token(self) -> str | None:
        """Get valid access token, refreshing if needed."""
        # Check if current token is still valid
        if self._token and time.time() < self._token_expiry:
            return self._token

        creds = self._load_credentials()
        if not creds:
            return None

        oauth_data = creds.get("claudeAiOauth", {})
        token = oauth_data.get("accessToken")
        expires_at = oauth_data.get("expiresAt", 0)

        if not token:
            logger.warning("No access token in credentials")
            return None

        # Check if token is expired
        if expires_at and time.time() > expires_at / 1000:  # expiresAt is in milliseconds
            logger.warning("Access token expired")
            # TODO: Implement token refresh using refreshToken
            return None

        self._token = token
        self._token_expiry = expires_at / 1000 if expires_at else time.time() + 3600

        return self._token

    def _get_headers(self) -> dict | None:
        """Get headers for API requests."""
        token = self._get_token()
        if not token:
            return None

        return {
            "Authorization": f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "oauth-2025-04-20",
            "anthropic-dangerous-direct-browser-access": "true",
            "Content-Type": "application/json",
        }

    def _api_request(
        self,
        method: str,
        endpoint: str,
        data: dict | None = None,
        timeout: float = 10.0,
    ) -> dict | None:
        """Make an API request.

        Args:
            method: HTTP method
            endpoint: API endpoint (relative to base URL)
            data: Request body data
            timeout: Request timeout

        Returns:
            Response JSON or None on error
        """
        headers = self._get_headers()
        if not headers:
            return None

        url = f"https://api.anthropic.com{endpoint}"

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.warning(f"API request failed: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error parsing API response: {e}")
            return None

    def get_usage(self, force_refresh: bool = False) -> UsageInfo | None:
        """Get current API usage information.

        Args:
            force_refresh: Force refresh from API

        Returns:
            UsageInfo or None on error
        """
        # Check cache
        now = time.time()
        if not force_refresh and self._usage_cache and (now - self._usage_cache_time) < _CACHE_TTL:
            return self._usage_cache

        # Fetch from API
        # Note: The actual endpoint may vary - this is a placeholder
        # based on typical OAuth API patterns
        data = self._api_request("GET", "/v1/usage")

        if not data:
            return self._usage_cache  # Return cached if available

        try:
            usage = UsageInfo(
                daily_spend_usd=data.get("daily_spend_usd", 0.0),
                monthly_spend_usd=data.get("monthly_spend_usd", 0.0),
                daily_limit_usd=data.get("daily_limit_usd"),
                monthly_limit_usd=data.get("monthly_limit_usd"),
                rate_limit_tier=data.get("rate_limit_tier"),
                rolling_window_seconds=data.get("rolling_window_seconds", 18000),  # 5 hours
                rolling_window_tokens=data.get("rolling_window_tokens", 0),
                rolling_window_limit=data.get("rolling_window_limit"),
                utilization_percent=data.get("utilization_percent", 0.0),
            )

            self._usage_cache = usage
            self._usage_cache_time = now
            return usage

        except Exception as e:
            logger.warning(f"Failed to parse usage data: {e}")
            return self._usage_cache

    def get_profile(self, force_refresh: bool = False) -> ProfileInfo | None:
        """Get user profile information.

        Args:
            force_refresh: Force refresh from API

        Returns:
            ProfileInfo or None on error
        """
        # Check cache
        now = time.time()
        if not force_refresh and self._profile_cache and (now - self._profile_cache_time) < _CACHE_TTL:
            return self._profile_cache

        # Fetch from API
        data = self._api_request("GET", "/v1/me")

        if not data:
            return self._profile_cache

        try:
            profile = ProfileInfo(
                user_id=data.get("id", ""),
                email=data.get("email", ""),
                name=data.get("name"),
                organization_id=data.get("organization_id"),
                organization_name=data.get("organization_name"),
            )

            self._profile_cache = profile
            self._profile_cache_time = now
            return profile

        except Exception as e:
            logger.warning(f"Failed to parse profile data: {e}")
            return self._profile_cache

    def get_organization_usage(self, org_id: str) -> dict | None:
        """Get organization usage details.

        Args:
            org_id: Organization ID

        Returns:
            Usage details or None
        """
        return self._api_request("GET", f"/v1/organizations/{org_id}/usage")

    def list_api_keys(self) -> list[dict]:
        """List available API keys."""
        data = self._api_request("GET", "/v1/api_keys")
        return data.get("data", []) if data else []

    def get_rate_limits(self) -> dict | None:
        """Get current rate limit information."""
        return self._api_request("GET", "/v1/rate_limits")


# Global instance
oauth_client = OAuthAPIClient()


# Convenience functions
def get_usage(force_refresh: bool = False) -> UsageInfo | None:
    """Get current API usage."""
    return oauth_client.get_usage(force_refresh)


def get_profile(force_refresh: bool = False) -> ProfileInfo | None:
    """Get user profile."""
    return oauth_client.get_profile(force_refresh)
