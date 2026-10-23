"""Assertion helpers whose failure messages explain what happened.

A bare `assert r.status_code == 201` fails with "assert 422 == 201" - you then have
to re-run the test to find out why. These helpers put the request and the response
body into the message.
"""

import httpx


def describe(response: httpx.Response) -> str:
    request = response.request
    return f"{request.method} {request.url.path} -> {response.status_code}: {response.text[:500]}"


def assert_status(response: httpx.Response, expected: int) -> None:
    assert response.status_code == expected, f"Expected HTTP {expected}, got {describe(response)}"


def assert_error(response: httpx.Response, status: int, code: str) -> dict:
    """Check an error response: status code, uniform JSON shape and machine-readable code."""
    assert_status(response, status)
    body = response.json()
    assert body.get("code") == code, f"Expected error code {code!r}, got {body!r}"
    assert isinstance(body.get("detail"), str), f"Error without a 'detail' message: {body!r}"
    assert body["detail"], f"Error with an empty 'detail' message: {body!r}"
    return body
