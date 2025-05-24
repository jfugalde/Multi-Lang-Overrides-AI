import logging
import os
import uuid
import urllib.parse
from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import Any, Dict, List, Optional, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3 import Retry


def _load_from_settings(name: str, default: Any = None) -> Any:
    try:
        config_mod = import_module("src.config")
        return getattr(config_mod, name, os.getenv(name, default))
    except ModuleNotFoundError:
        return os.getenv(name, default)


def _summarize(obj: Union[Dict[str, Any], List[Any], Any]) -> Any:
    if isinstance(obj, list) and len(obj) > 5:
        return {"count": len(obj), "sample": obj[:5]}
    if isinstance(obj, dict):
        first_keys = list(obj.keys())[:5]
        return {k: obj[k] for k in first_keys}
    return obj


_LOG = logging.getLogger(__name__)


class BigCommerceClient:
    _STORE_GQL_PUBLIC = "https://store-{hash}.mybigcommerce.com/graphql"
    _REST_ENV_MAP = {
        "production": "https://api.bigcommerce.com/stores/{hash}",
        "staging":    "https://api.staging.zone/stores/{hash}",
        "integration": "https://api.integration.zone/stores/{hash}",
        "sandbox":    "https://api.bigcommerce.com/stores/{hash}",
    }

    def __init__(
        self,
        *,
        environment: str = "production",
        debug: bool = False,
        timeout: int = 10,
        retries: int = 3,
        backoff: float = 0.5,
    ) -> None:
        self.store_hash: str = _load_from_settings("BC_STORE_HASH")
        self.access_token: str = _load_from_settings("BC_ACCESS_TOKEN")
        self.client_id: str = _load_from_settings("CLIENT_ID")
        self.client_secret: str = _load_from_settings("CLIENT_SECRET")
        self.channel_id: int = int(_load_from_settings("BC_CHANNEL_ID", 1))

        if not self.store_hash or not self.access_token:
            raise ValueError("BC_STORE_HASH y BC_ACCESS_TOKEN son obligatorios")

        self.base_url = self._REST_ENV_MAP.get(
            environment.lower(), self._REST_ENV_MAP["production"]
        ).format(hash=self.store_hash)

        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Auth-Client": self.client_id,
                "X-Auth-Token": self.access_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        retry_cfg = Retry(
            total=retries,
            backoff_factor=backoff,
            status_forcelist=[429, 499, 500, 502, 503, 504],
            allowed_methods=frozenset(
                ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
            ),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry_cfg))

        if debug:
            logging.getLogger("requests").setLevel(logging.DEBUG)
            logging.getLogger("urllib3").setLevel(logging.DEBUG)

        _LOG.debug("BC client init → base_url=%s", self.base_url)

    def _customer_token(self) -> Optional[str]:
        endpoint = "/storefront/api-token"
        expires_at = int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp())
        payload = {"channel_id": self.channel_id, "expires_at": expires_at}

        data = self._request("POST", endpoint, json=payload)
        token = (data or {}).get("data", {}).get("token")
        if not token:
            _LOG.error("No JWT received (payload=%s)", _summarize(data))
        return token

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        version: str = "v3",
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Union[Dict[str, Any], List[Any], None]:
        url = (
            f"{self.base_url}/{version}{endpoint}"
            if endpoint.startswith("/")
            else f"{self.base_url}/{version}/{endpoint}"
        )

        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)

        req_id = uuid.uuid4().hex
        start = datetime.now()

        headers = {**(extra_headers or {})}

        _LOG.info("%s %s | id=%s", method, url, req_id)

        try:
            resp = self.session.request(
                method,
                url,
                json=json,
                timeout=self.timeout,
                headers=headers or None,
            )
            resp.raise_for_status()
            elapsed = (datetime.now() - start).total_seconds()

            try:
                body = resp.json()
            except json.JSONDecodeError:
                _LOG.error("Non-JSON response id=%s → %s…", req_id, resp.text[:200])
                return None

            _LOG.debug(
                "%s %s | %s %.2fs | body=%s",
                method,
                url,
                resp.status_code,
                elapsed,
                _summarize(body),
            )
            return body
        except requests.RequestException as exc:
            _LOG.error("HTTP fail id=%s → %s", req_id, exc)
            return None

    def rest(
        self,
        endpoint: str,
        method: str = "GET",
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        use_v3: bool = True,
    ) -> Union[Dict[str, Any], List[Any], None]:
        version = "v3" if use_v3 else "v2"
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        return self._request(method, endpoint, params=params, json=json, version=version)

    def make_request(self, method: str, endpoint: str, **kw):
        return self.rest(endpoint, method, **kw)

    def graphql(
        self,
        query: str,
        *,
        variables: Optional[Dict[str, Any]] = None,
        admin: bool = False,
        locale: str = "en",
        override_base: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:

        if override_base:
            url = f"{override_base.rstrip('/')}/graphql"
        elif admin:
            url = f"{self.base_url}/graphql"
        else:
            url = self._STORE_GQL_PUBLIC.format(hash=self.store_hash)

        headers = {
            "Accept-Language": locale,
            "Authorization": f"Bearer {self._customer_token()}",
        }

        payload = {"query": query, "variables": variables or {}}
        req_id = uuid.uuid4().hex
        _LOG.info("GraphQL → %s | id=%s", url, req_id)

        try:
            resp = self.session.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )
            resp.raise_for_status()
            body = resp.json()

            if body.get("errors"):
                _LOG.error("GraphQL errors id=%s → %s", req_id, body["errors"])
                return None

            _LOG.debug("GraphQL OK id=%s → %s", req_id, _summarize(body))
            return body
        except requests.RequestException as exc:
            _LOG.error("GraphQL HTTP fail id=%s → %s", req_id, exc)
            return None