"""The real Azure OpenAI and Supabase Storage adapters, against mocked HTTP (no network)."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import httpx
import httpx2
import openai

from app.schemas.resume import ResumeExtraction
from app.services.llm import AzureOpenAIClient, LLMInvalidOutputError, LLMUnavailableError
from app.services.storage import StorageError, SupabaseStorage

EMPTY_EXTRACTION = {
    "contact": {"full_name": "Ada", "email": None, "phone": None, "location": None, "links": []},
    "education": [],
    "experience": [],
    "projects": [],
    "skills": [],
}


def chat_completion(content: str | None, refusal: str | None = None) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content, "refusal": refusal},
            }
        ],
    }


class AzureOpenAIClientTests(unittest.TestCase):
    def client_returning(self, status: int, body: dict) -> AzureOpenAIClient:
        self.requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(status, json=body)

        client = AzureOpenAIClient("https://example.openai.azure.com", "test-key", "resume-model", "2024-10-21")
        client._client = openai.AzureOpenAI(
            azure_endpoint="https://example.openai.azure.com",
            api_key="test-key",
            api_version="2024-10-21",
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        return client

    def test_parses_structured_output_with_json_schema(self) -> None:
        client = self.client_returning(200, chat_completion(json.dumps(EMPTY_EXTRACTION)))

        result = client.extract(ResumeExtraction, "instructions", "content")

        self.assertEqual("Ada", result.contact.full_name)
        sent = json.loads(self.requests[0].content)
        self.assertEqual("json_schema", sent["response_format"]["type"])
        self.assertTrue(sent["response_format"]["json_schema"]["strict"])
        self.assertIn("/deployments/resume-model/", str(self.requests[0].url))

    def test_output_not_matching_schema_is_invalid(self) -> None:
        client = self.client_returning(200, chat_completion(json.dumps({"contact": {}})))

        with self.assertRaises(LLMInvalidOutputError):
            client.extract(ResumeExtraction, "instructions", "content")

    def test_refusal_is_invalid(self) -> None:
        client = self.client_returning(200, chat_completion(None, refusal="I can't help with that."))

        with self.assertRaises(LLMInvalidOutputError):
            client.extract(ResumeExtraction, "instructions", "content")

    def test_provider_errors_are_unavailable(self) -> None:
        for status in (401, 429, 500):
            with self.subTest(status=status):
                client = self.client_returning(status, {"error": {"message": "nope"}})
                with self.assertRaises(LLMUnavailableError):
                    client.extract(ResumeExtraction, "instructions", "content")


class SupabaseStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = SupabaseStorage("https://proj.supabase.co/", "secret-key", "resumes")

    def test_requests_use_private_object_url_and_secret_key(self) -> None:
        response = httpx2.Response(200, content=b"%PDF-", request=httpx2.Request("GET", "https://x"))
        with mock.patch.object(httpx2, "request", return_value=response) as request:
            self.storage.put("user/id.pdf", b"%PDF-", "application/pdf")
            self.assertEqual(b"%PDF-", self.storage.get("user/id.pdf"))
            self.storage.delete("user/id.pdf")

        methods = [call.args[0] for call in request.call_args_list]
        self.assertEqual(["POST", "GET", "DELETE"], methods)
        url = request.call_args_list[0].args[1]
        self.assertEqual("https://proj.supabase.co/storage/v1/object/resumes/user/id.pdf", url)
        headers = request.call_args_list[0].kwargs["headers"]
        self.assertEqual("secret-key", headers["apikey"])
        self.assertEqual("application/pdf", headers["Content-Type"])

    def test_http_errors_become_storage_errors(self) -> None:
        response = httpx2.Response(403, request=httpx2.Request("GET", "https://x"))
        with mock.patch.object(httpx2, "request", return_value=response):
            with self.assertRaises(StorageError):
                self.storage.get("user/id.pdf")


if __name__ == "__main__":
    unittest.main()
