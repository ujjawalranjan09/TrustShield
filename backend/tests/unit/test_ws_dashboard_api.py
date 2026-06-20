"""Tests for WebSocket dashboard endpoint."""

import json

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app, raise_server_exceptions=False)


def test_websocket_connect_and_ping():
    with client.websocket_connect("/api/v1/ws/dashboard") as ws:
        ws.send_text("ping")
        data = ws.receive_text()
        msg = json.loads(data)
        assert msg["type"] == "pong"


def test_websocket_connect_and_disconnect():
    with client.websocket_connect("/api/v1/ws/dashboard") as ws:
        ws.send_text("ping")
        resp = ws.receive_text()
        msg = json.loads(resp)
        assert msg["type"] == "pong"
