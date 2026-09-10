#!/usr/bin/env python3
"""Read-only DeepSeek authentication check; never performs model inference.

Output is deliberately a finite projection, not the supplier response, secret,
balance amount, model-health claim or a spend-admission receipt.
"""
from __future__ import annotations

import json
import os
import re
import sys
from decimal import Decimal
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ENDPOINT = "https://api.deepseek.com/user/balance"
MAX_BYTES = 65536


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def closed_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def project_balance(raw: bytes) -> dict:
    if len(raw) > MAX_BYTES:
        raise ValueError("oversized response")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=closed_pairs)
    if not isinstance(data, dict) or type(data.get("is_available")) is not bool:
        raise ValueError("invalid availability")
    rows = data.get("balance_infos")
    if not isinstance(rows, list) or not rows:
        raise ValueError("missing balances")
    currencies = set()
    positive = False
    for row in rows:
        if not isinstance(row, dict) or row.get("currency") not in ("CNY", "USD"):
            raise ValueError("invalid currency")
        if row["currency"] in currencies:
            raise ValueError("duplicate currency")
        currencies.add(row["currency"])
        amounts = []
        for name in ("total_balance", "granted_balance", "topped_up_balance"):
            value = row.get(name)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,18}(?:\.[0-9]{1,12})?", value):
                raise ValueError("invalid balance")
            amounts.append(Decimal(value))
        if amounts[0] != amounts[1] + amounts[2]:
            raise ValueError("inconsistent balance")
        positive = positive or amounts[0] > 0
    available = data["is_available"] and positive
    return {"authentication": "passed", "supplier_available": available,
            "positive_balance": positive, "currencies": sorted(currencies),
            "status": "passed" if available else "unavailable"}


def check(key: str, opener=None) -> dict:
    if not key or len(key) > 1024 or not re.fullmatch(r"[\x21-\x7e]+", key):
        return {"status": "credential_missing_or_invalid"}
    # No proxy environment or redirects may forward the Authorization header.
    opener = opener or build_opener(ProxyHandler({}), NoRedirect())
    request = Request(ENDPOINT, headers={"Authorization": "Bearer " + key,
                                       "Accept": "application/json"}, method="GET")
    try:
        with opener.open(request, timeout=15) as response:
            if response.status != 200:
                return {"status": "unexpected_http_status"}
            return project_balance(response.read(MAX_BYTES + 1))
    except HTTPError as exc:
        code = exc.code
        exc.close()
        return {"status": "http_error", "http_status": code if type(code) is int and 100 <= code <= 599 else 0}
    except (URLError, TimeoutError, OSError, HTTPException):
        return {"status": "transport_error"}
    except (ValueError, TypeError, ArithmeticError, RecursionError):
        return {"status": "invalid_response"}


def main() -> int:
    result = check(os.environ.pop("PR_AGENT_DEEPSEEK_API_KEY", ""))
    receipt = {"schema": "lmdj.pr-agent-credential-preflight.v1", "provider": "deepseek",
               "selected_model": "deepseek-flash", "operation": "GET /user/balance",
               "inference_requests": 0, "funding_admission": "not_evaluated",
               "runtime_secret_provisioned": False, **result}
    if result["status"] != "passed":
        receipt["why"] = "Dedicated API authentication/availability was not established."
        receipt["remedy"] = "Check the dedicated DeepSeek API key and account through the provider console; do not print credentials or retry inference."
    print(json.dumps(receipt, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
