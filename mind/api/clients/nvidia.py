"""NVIDIA NIM (NVIDIA API) ModelClient integration."""

import os
from typing import Any, Dict, Optional
import backoff
from adalflow.components.model_client.openai_client import (
    OpenAIClient,
    log,
)
from adalflow.core import ModelType
from adalflow.core.types import EmbedderOutput, Embedding
from openai import (
    APITimeoutError,
    InternalServerError,
    RateLimitError,
    UnprocessableEntityError,
    BadRequestError,
)


def convert_inputs_to_api_kwargs(
    self,
    input: Optional[Any] = None,
    model_kwargs: Dict = {},
    model_type: ModelType = ModelType.UNDEFINED,
) -> Dict:
    self.generate = False
    final_model_kwargs = model_kwargs.copy() if model_kwargs else {}
    if model_type == ModelType.EMBEDDER:
        final_model_kwargs["input"] = input
        input_type = model_kwargs.get("input_type", "query")
        if "extra_body" not in final_model_kwargs:
            final_model_kwargs["extra_body"] = {}
        if "input_type" not in final_model_kwargs["extra_body"]:
            final_model_kwargs["extra_body"]["input_type"] = input_type
        return final_model_kwargs
    elif model_type in (ModelType.LLM, ModelType.LLM_REASONING):
        if input is not None and input != "":
            if model_kwargs.get("generate", False):
                final_model_kwargs["prompt"] = input
                self.generate = True
            else:
                if isinstance(input, str):
                    input = [{"role": "user", "content": input}]
                    final_model_kwargs["messages"] = input
                elif not isinstance(input, list):
                    raise ValueError("Input must be a string or a list of messages")
            return final_model_kwargs
        else:
            raise ValueError("Input must be text")
    else:
        raise ValueError(f"model_type {model_type} is not supported")


@backoff.on_exception(
    backoff.expo,
    (
        APITimeoutError,
        InternalServerError,
        RateLimitError,
        UnprocessableEntityError,
        BadRequestError,
    ),
    max_tries=5,
)
async def acall(
    self,
    api_kwargs: dict = None,
    model_type: ModelType = ModelType.UNDEFINED,
):
    if self.async_client is None:
        self.init_async_client()
        if self.async_client is None:
            raise RuntimeError("Async client is not initialized")
    api_kwargs = api_kwargs or {}
    if model_type == ModelType.EMBEDDER:
        return await self.async_client.embeddings.create(**api_kwargs)
    if model_type in (ModelType.LLM, ModelType.LLM_REASONING):
        if "stream" in api_kwargs and api_kwargs.get("stream", False):
            log.debug("streaming call")
            self.response_parser = self.streaming_response_parser
            return await self.async_client.chat.completions.create(**api_kwargs)
        else:
            log.debug("non-streaming call")
            self.response_parser = self.non_streaming_response_parser
            return await self.async_client.chat.completions.create(**api_kwargs)
    else:
        raise ValueError(f"model_type {model_type} is not supported")


@backoff.on_exception(
    backoff.expo,
    (
        APITimeoutError,
        InternalServerError,
        RateLimitError,
        UnprocessableEntityError,
        BadRequestError,
    ),
    max_tries=5,
)
def call(
    self,
    api_kwargs: dict = None,
    model_type: ModelType = ModelType.UNDEFINED,
):
    api_kwargs = api_kwargs or {}
    if not self.sync_client:
        self.init_sync_client()
        if self.sync_client is None:
            raise RuntimeError("Sync client is not initialized")

    if model_type == ModelType.EMBEDDER:
        return self.sync_client.embeddings.create(**api_kwargs)
    if model_type in (ModelType.LLM, ModelType.LLM_REASONING):
        if "stream" in api_kwargs and api_kwargs.get("stream", False):
            log.debug("streaming call")
            self.response_parser = self.streaming_response_parser_sync
            return self.sync_client.chat.completions.create(**api_kwargs)
        else:
            log.debug("non-streaming call")
            self.response_parser = self.non_streaming_response_parser
            return self.sync_client.chat.completions.create(**api_kwargs)
    else:
        raise ValueError(f"model_type {model_type} is not supported")


def parse_embedding_response(self, response: Dict[str, Any]) -> EmbedderOutput:
    try:
        data = response["data"] if isinstance(response, dict) else response.data
        return EmbedderOutput(
            data=[
                Embedding(
                    embedding=item["embedding"] if isinstance(item, dict) else item.embedding,
                    index=i
                )
                for i, item in enumerate(data)
            ]
        )
    except Exception as e:
        log.error(f"Error parsing NVIDIA embedding response: {e}")
        return EmbedderOutput(data=[], error=str(e), raw_response=response)


class NvidiaClient(OpenAIClient):
    """NVIDIA NIM / API ModelClient for completion, chat, and embeddings.

    API endpoint: https://integrate.api.nvidia.com/v1
    API key env: NVIDIA_API_KEY
    """

    def __init__(self, *args, **kwargs):
        base_url = kwargs.pop("base_url", None) or os.environ.get(
            "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
        )
        api_key = kwargs.pop("api_key", None) or os.environ.get(
            "NVIDIA_API_KEY", "nvapi-dummy"
        )
        super().__init__(*args, base_url=base_url, api_key=api_key, **kwargs)


NvidiaClient.convert_inputs_to_api_kwargs = convert_inputs_to_api_kwargs
NvidiaClient.parse_embedding_response = parse_embedding_response
NvidiaClient.call = call
NvidiaClient.acall = acall

