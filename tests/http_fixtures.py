"""Synthetic HTTP responses; never connects to Garmin."""

import base64
import json
import time
from collections import deque
from io import BytesIO

import requests
from requests.adapters import BaseAdapter


def token(expires=None):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": expires or time.time() + 86400}).encode())
    return "synthetic." + payload.decode().rstrip("=") + ".signature"


class ScriptedHTTP(BaseAdapter):
    def __init__(self, *responses):
        self.responses = deque(responses)
        self.requests = []

    def send(self, request, **kwargs):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        value = self.responses.popleft()
        if isinstance(value, Exception):
            raise value
        status, body, *headers = value
        response = requests.Response()
        response.status_code = status
        response.url = request.url
        response.request = request
        response.headers.update(headers[0] if headers else {})
        content = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        response.raw = BytesIO(content)
        return response

    def close(self):
        pass
