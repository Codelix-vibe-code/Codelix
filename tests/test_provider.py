import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from vybelix.config import ProviderSettings, validate_config
from vybelix.config import load_env_file
from vybelix.providers import (
    AccessDeniedError,
    AuthenticationError,
    GeminiAdapter,
    GroqAdapter,
    NvidiaAdapter,
    InvalidResponseError,
    ModelNotFoundError,
    ModelRouter,
    NetworkError,
    RateLimitError,
    RoutingError,
    TransientProviderError,
    build_router,
)


class FakeResponse:
    def __init__(self, data):
        self.data = json.dumps(data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.data


def interaction(text="réponse", status="completed"):
    return {
        "status": status,
        "steps": [{"type": "model_output", "content": [{"type": "text", "text": text}]}],
    }


class GeminiAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = GeminiAdapter(
            ProviderSettings("https://generativelanguage.googleapis.com/v1", "GEMINI_API_KEY"),
            api_key="test-secret",
            timeout_seconds=17,
        )

    def test_translates_common_messages_and_interactions_response(self):
        with patch("vybelix.providers.gemini._open_without_redirect", return_value=FakeResponse(interaction())) as open_url:
            self.assertEqual(self.adapter.complete(
                [{"role": "system", "content": "Sois concis."}, {"role": "user", "content": "Bonjour"}],
                "gemini-test",
                {"max_output_tokens": 200, "thinking_level": "low"},
            ), "réponse")
        request = open_url.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "https://generativelanguage.googleapis.com/v1/interactions")
        self.assertEqual(request.get_header("X-goog-api-key"), "test-secret")
        self.assertNotIn("test-secret", request.full_url)
        self.assertEqual(body["model"], "gemini-test")
        self.assertEqual(body["input"], "User:\nBonjour")
        self.assertEqual(body["system_instruction"], "Sois concis.")
        self.assertFalse(body["store"])
        self.assertEqual(body["generation_config"], {"max_output_tokens": 200, "thinking_level": "low"})
        self.assertEqual(open_url.call_args.kwargs["timeout"], 17)

    def test_rejects_missing_key_without_network_call(self):
        adapter = GeminiAdapter(self.adapter.settings, api_key="")
        with patch("vybelix.providers.gemini._open_without_redirect") as open_url:
            with self.assertRaises(AuthenticationError):
                adapter.complete([{"role": "user", "content": "hi"}], "model")
            open_url.assert_not_called()

    def test_rejects_malformed_interaction(self):
        with patch("vybelix.providers.gemini._open_without_redirect", return_value=FakeResponse({"status": "completed"})):
            with self.assertRaises(InvalidResponseError):
                self.adapter.complete([{"role": "user", "content": "hi"}], "model")

    def test_rejects_non_completed_interaction(self):
        with patch("vybelix.providers.gemini._open_without_redirect", return_value=FakeResponse(interaction(status="incomplete"))):
            with self.assertRaises(InvalidResponseError):
                self.adapter.complete([{"role": "user", "content": "hi"}], "model")

    def test_retries_are_not_hidden_in_adapter(self):
        with patch("vybelix.providers.gemini._open_without_redirect", side_effect=TimeoutError):
            with self.assertRaises(NetworkError):
                self.adapter.complete([{"role": "user", "content": "hi"}], "model")

    def test_maps_http_statuses(self):
        cases = [
            (401, AuthenticationError),
            (403, AccessDeniedError),
            (404, ModelNotFoundError),
            (408, NetworkError),
            (429, RateLimitError),
            (503, TransientProviderError),
        ]
        for status, error_type in cases:
            with self.subTest(status=status):
                error = HTTPError("https://example.invalid", status, "failure", {}, io.BytesIO(b"secret body"))
                with patch("vybelix.providers.gemini._open_without_redirect", side_effect=error):
                    with self.assertRaises(error_type) as raised:
                        self.adapter.complete([{"role": "user", "content": "hi"}], "model")
                self.assertNotIn("secret body", str(raised.exception))

    def test_maps_network_error(self):
        with patch("vybelix.providers.gemini._open_without_redirect", side_effect=URLError("offline")):
            with self.assertRaises(NetworkError):
                self.adapter.complete([{"role": "user", "content": "hi"}], "model")

    def test_rejects_unrecognized_generation_options(self):
        with self.assertRaises(ValueError):
            GeminiAdapter._request_body([{"role": "user", "content": "hi"}], "model", {"top_p": 0.5})


class CompatibleProviderTests(unittest.TestCase):
    def test_nvidia_and_groq_use_compatible_chat_api(self):
        cases = [
            (NvidiaAdapter, "https://integrate.api.nvidia.com/v1", "nvidia"),
            (GroqAdapter, "https://api.groq.com/openai/v1", "groq"),
        ]
        for adapter_type, base_url, name in cases:
            with self.subTest(provider=name):
                adapter = adapter_type(ProviderSettings(base_url, f"{name.upper()}_API_KEY"), api_key="test-secret")
                response = FakeResponse({"choices": [{"message": {"content": "ok"}}]})
                with patch("vybelix.providers.openai_compatible.build_opener") as opener:
                    opener.return_value.open.return_value.__enter__.return_value = response
                    self.assertEqual(adapter.complete([{"role": "user", "content": "salut"}], "model-id"), "ok")
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(request.full_url, f"{base_url}/chat/completions")
                self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
                body = json.loads(request.data)
                self.assertEqual(body["messages"][0]["content"], "salut")
                self.assertFalse(body["stream"])

    def test_env_loader_preserves_existing_variables_and_supports_quotes(self):
        import os
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("CODELIX_TEST_SECRET='private value'\nexport CODELIX_TEST_OTHER=value # note\n", encoding="utf-8")
            with patch.dict(os.environ, {"CODELIX_TEST_SECRET": "process-value"}, clear=False):
                load_env_file(env_path)
                self.assertEqual(os.environ["CODELIX_TEST_SECRET"], "process-value")
                self.assertEqual(os.environ["CODELIX_TEST_OTHER"], "value")


class FakeProvider:
    name = "fake"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages, model, options=None):
        self.calls.append(model)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class RouterTests(unittest.TestCase):
    def test_falls_back_after_rate_limit(self):
        first = FakeProvider(RateLimitError("limit", provider="fake", model="one", status_code=429, fallback=True))
        second = FakeProvider("ok")
        router = ModelRouter({"first": first, "second": second}, {"planner": ["first:one", "second:two"]})
        self.assertEqual(router.complete("planner", [{"role": "user", "content": "hi"}]), "ok")
        self.assertEqual(first.calls, ["one"])
        self.assertEqual(second.calls, ["two"])
        self.assertEqual(router.last_trace[-1].outcome, "success")

    def test_retries_timeout_once_then_falls_back(self):
        first = FakeProvider(
            NetworkError("timeout", provider="first", model="one", retryable=True, fallback=True),
            NetworkError("timeout", provider="first", model="one", retryable=True, fallback=True),
        )
        second = FakeProvider("ok")
        router = ModelRouter({"first": first, "second": second}, {"coder": ["first:one", "second:two"]})
        self.assertEqual(router.complete("coder", [{"role": "user", "content": "hi"}]), "ok")
        self.assertEqual(first.calls, ["one", "one"])

    def test_authentication_failure_stops_without_fallback(self):
        first = FakeProvider(AuthenticationError("bad key", provider="first", model="one", fatal=True))
        second = FakeProvider("must not be called")
        router = ModelRouter({"first": first, "second": second}, {"planner": ["first:one", "second:two"]})
        with self.assertRaises(RoutingError):
            router.complete("planner", [{"role": "user", "content": "hi"}])
        self.assertEqual(second.calls, [])

    def test_403_stops_without_fallback(self):
        first = FakeProvider(AccessDeniedError("denied", provider="first", model="one", fatal=True))
        second = FakeProvider("must not be called")
        router = ModelRouter({"first": first, "second": second}, {"planner": ["first:one", "second:two"]})
        with self.assertRaises(RoutingError):
            router.complete("planner", [{"role": "user", "content": "hi"}])
        self.assertEqual(second.calls, [])

    def test_rejects_no_configured_candidates(self):
        router = ModelRouter({}, {"planner": []})
        with self.assertRaises(RoutingError):
            router.complete("planner", [{"role": "user", "content": "hi"}])

    def test_builds_router_from_validated_config(self):
        config = validate_config({
            "schema_version": "1.0",
            "runtime": {"request_timeout_seconds": 45, "network_retries": 0},
            "providers": {"gemini": {"base_url": "https://generativelanguage.googleapis.com/v1", "api_key_env": "GEMINI_API_KEY"}},
            "models": {"planner": ["gemini:gemini-test"]},
        })
        router = build_router(config)
        self.assertIsInstance(router.providers["gemini"], GeminiAdapter)
        self.assertEqual(router.providers["gemini"].timeout_seconds, 45)
        self.assertEqual(router.transient_retries, 0)


if __name__ == "__main__":
    unittest.main()
