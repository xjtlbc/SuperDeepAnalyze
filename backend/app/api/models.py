from fastapi import APIRouter
from pydantic import BaseModel

from app.models.config import ModelConfig
from app.models.crud import save_model_config, load_model_configs, bump_config_version
from app.models.provider_registry import get_all_presets, get_preset

router = APIRouter(prefix="/api/models", tags=["models"])


class ModelConfigRequest(BaseModel):
    base_url: str
    model_name: str
    api_key: str = ""
    max_tokens: int = 8192
    dimension: int | None = None
    enabled: bool = True
    provider_type: str = "openai"


class ModelConfigResponse(BaseModel):
    role: str
    base_url: str
    model_name: str
    max_tokens: int
    dimension: int | None
    enabled: bool
    config_version: int
    provider_type: str = "openai"

    class Config:
        from_attributes = True


class TestConnectionRequest(BaseModel):
    base_url: str
    model_name: str
    api_key: str
    provider_type: str = "openai"


@router.get("/config")
async def get_model_config():
    """Get current model configuration."""
    configs = load_model_configs()
    if configs is None:
        return {"configured": False}
    return {
        "configured": True,
        "main": {**configs.main.model_dump_safe(), "enabled": True},
        "lightweight": {**configs.lightweight.model_dump_safe(), "enabled": True} if configs.lightweight else None,
        "embedding": {**configs.embedding.model_dump_safe(), "enabled": True} if configs.embedding else None,
        "vlm": {**configs.vlm.model_dump_safe(), "enabled": True} if configs.vlm else None,
        "rrf_k": configs.rrf_k,
        "agent_max_iterations": configs.agent_max_iterations,
    }


@router.put("/config/{role}")
async def update_model_config(role: str, data: ModelConfigRequest):
    """Update model configuration for a role."""
    mc = ModelConfig(
        base_url=data.base_url,
        model_name=data.model_name,
        api_key=data.api_key,
        max_tokens=data.max_tokens,
        dimension=data.dimension,
        provider_type=data.provider_type,
    )
    save_model_config(role, mc, enabled=data.enabled)
    new_version = bump_config_version()
    return {"role": role, "config_version": new_version}


@router.get("/presets")
async def list_presets():
    """List all available provider presets."""
    presets = get_all_presets()
    return [
        {
            "id": p.id,
            "name": p.name,
            "adapter": p.adapter,
            "base_url": p.base_url_cn or p.base_url,
            "is_local": p.is_local,
            "features": p.features,
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "context_window": m.context_window,
                    "supports_tools": m.supports_tools,
                    "supports_vision": m.supports_vision,
                }
                for m in p.models
            ],
        }
        for p in presets
    ]


@router.get("/presets/{provider_id}")
async def get_preset_detail(provider_id: str):
    """Get details for a specific provider preset."""
    preset = get_preset(provider_id)
    if not preset:
        return {"error": "Provider not found"}
    return {
        "id": preset.id,
        "name": preset.name,
        "adapter": preset.adapter,
        "base_url": preset.base_url_cn or preset.base_url,
        "is_local": preset.is_local,
        "features": preset.features,
        "models": [
            {
                "id": m.id,
                "name": m.name,
                "context_window": m.context_window,
                "max_output_tokens": m.max_output_tokens,
                "supports_tools": m.supports_tools,
                "supports_vision": m.supports_vision,
            }
            for m in preset.models
        ],
    }


@router.post("/test-connection")
async def test_connection(data: TestConnectionRequest):
    """Test model connection by making a real lightweight API call."""
    if data.provider_type == "anthropic":
        from app.models.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider(
            base_url=data.base_url,
            model_name=data.model_name,
            api_key=data.api_key,
            max_tokens=10,
        )
    else:
        from app.models.openai_provider import OpenAIProvider
        provider = OpenAIProvider(
            base_url=data.base_url,
            model_name=data.model_name,
            api_key=data.api_key,
            max_tokens=10,
        )
    try:
        response = await provider.chat(
            messages=[{"role": "user", "content": "Hi"}],
            temperature=0,
        )
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        model_id = response.get("model", data.model_name)
        return {"connected": True, "model": model_id, "response_preview": content[:50]}
    except Exception as e:
        return {"connected": False, "error": str(e)}
