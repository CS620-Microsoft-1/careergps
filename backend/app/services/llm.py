"""The only module that talks to the LLM provider (ADR-003). Features depend on LLMClient."""
import logging
from typing import Protocol, TypeVar

import openai
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

TIMEOUT_SECONDS = 60


class LLMUnavailableError(Exception):
    """Provider timeout, outage, quota or configuration problem."""


class LLMInvalidOutputError(Exception):
    """The model answered, but not in the requested schema. The message lists what was wrong."""


class LLMClient(Protocol):
    name: str

    def extract(self, schema: type[T], instructions: str, content: str) -> T: ...


class AzureOpenAIClient:
    def __init__(self, endpoint: str, api_key: str, deployment: str, api_version: str) -> None:
        self.name = f"azure-openai:{deployment}"
        self._deployment = deployment
        self._client = openai.AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            timeout=TIMEOUT_SECONDS,
            max_retries=2,
        )

    def extract(self, schema: type[T], instructions: str, content: str) -> T:
        try:
            completion = self._client.chat.completions.parse(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": content},
                ],
                response_format=schema,
                temperature=0,
            )
        except ValidationError as error:
            raise LLMInvalidOutputError(str(error)) from error
        except (openai.LengthFinishReasonError, openai.ContentFilterFinishReasonError) as error:
            raise LLMInvalidOutputError(type(error).__name__) from error
        except openai.OpenAIError as error:
            # Never log the prompt or response: they contain résumé text.
            logger.warning("LLM call failed: %s", type(error).__name__)
            raise LLMUnavailableError(type(error).__name__) from error

        message = completion.choices[0].message
        if message.parsed is None:
            raise LLMInvalidOutputError("The model refused or returned no structured output.")
        return message.parsed
