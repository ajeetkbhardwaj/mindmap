import os
import pytest
from map.code_intel.parser import CodeParser
from mind.api.clients.nvidia import NvidiaClient
from mind.api.config import get_model_config, load_generator_config, get_embedder_type
from adalflow.core import ModelType

def test_nvidia_client_initialization():
    client = NvidiaClient(api_key="test-nv-key", base_url="https://integrate.api.nvidia.com/v1")
    assert "integrate.api.nvidia.com" in str(client.sync_client.base_url)

def test_nvidia_client_input_conversion():
    client = NvidiaClient(api_key="test-nv-key")
    
    # LLM messages input
    llm_kwargs = client.convert_inputs_to_api_kwargs(
        input="Explain graph database",
        model_kwargs={"model": "nvidia/nemotron-3.5-bolt-e4b"},
        model_type=ModelType.LLM,
    )
    assert llm_kwargs["model"] == "nvidia/nemotron-3.5-bolt-e4b"
    assert llm_kwargs["messages"][0]["content"] == "Explain graph database"

    # Embedder input
    embed_kwargs = client.convert_inputs_to_api_kwargs(
        input=["sample text"],
        model_kwargs={"model": "nvidia/nemotron-3.5-embed-1b"},
        model_type=ModelType.EMBEDDER,
    )
    assert embed_kwargs["input"] == ["sample text"]
    assert embed_kwargs["extra_body"]["input_type"] == "query"

def test_nvidia_provider_configuration():
    # Verify generator config contains nvidia
    gen_config = load_generator_config()
    assert "nvidia" in gen_config.get("providers", {})
    nv_conf = gen_config["providers"]["nvidia"]
    assert nv_conf["default_model"] == "nvidia/nemotron-3.5-bolt-e4b"
    assert nv_conf["model_client"].__name__ == "NvidiaClient"

    # Verify get_model_config resolves nvidia
    cfg = get_model_config(provider="nvidia")
    assert cfg["model_client"].__name__ == "NvidiaClient"
