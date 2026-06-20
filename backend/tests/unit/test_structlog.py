"""Unit tests for structured logging and trace correlation."""

import logging
import pytest


class TestRequestIDFormatter:
    def test_format_includes_request_id(self):
        from app.middleware.request_id import RequestIDFormatter, request_id_ctx_var

        formatter = RequestIDFormatter("%(request_id)s %(message)s")
        token = request_id_ctx_var.set("test-req-123")
        try:
            record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
            result = formatter.format(record)
            assert "test-req-123" in result
        finally:
            request_id_ctx_var.reset(token)

    def test_format_includes_trace_id(self):
        from app.middleware.request_id import RequestIDFormatter, trace_id_ctx_var

        formatter = RequestIDFormatter("%(trace_id)s %(message)s")
        token = trace_id_ctx_var.set("abc123")
        try:
            record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
            result = formatter.format(record)
            assert "abc123" in result
        finally:
            trace_id_ctx_var.reset(token)

    def test_format_default_when_no_context(self):
        from app.middleware.request_id import RequestIDFormatter, request_id_ctx_var

        formatter = RequestIDFormatter("%(request_id)s %(message)s")
        # Reset to default
        token = request_id_ctx_var.set("-")
        try:
            record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
            result = formatter.format(record)
            assert "-" in result
        finally:
            request_id_ctx_var.reset(token)


class TestTraceCorrelation:
    def test_get_trace_ids_returns_defaults_when_no_otel(self):
        from app.middleware.request_id import _get_trace_ids

        trace_id, span_id = _get_trace_ids()
        assert trace_id == "-"
        assert span_id == "-"
