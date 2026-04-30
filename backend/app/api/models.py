from fastapi import APIRouter
from pydantic import BaseModel

from app.models.config import ModelConfig
from app.models.crud import save_model_config, load_model_configs, bump_config_version

router = APIRouter(prefix="/api/models", tags=["models"])


class ModelConfigRequest(BaseModel):
    base_url: str
    model_name: str
    api_key: str = ""
    max_tokens: int = 8192
    dimension: int | None = None
    enabled: bool = True


class ModelConfigResponse(BaseModel):
    role: str
    base_url: str
    model_name: str
    max_tokens: int
    dimension: int | None
    enabled: bool
    config_version: int

    class Config:
        from_attributes = True


class TestConnectionRequest(BaseModel):
    base_url: str
    model_name: str
    api_key: str


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
    )
    save_model_config(role, mc, enabled=data.enabled)
    new_version = bump_config_version()
    return {"role": role, "config_version": new_version}


@router.post("/test-connection")
async def test_connection(data: TestConnectionRequest):
    """Test model connection by making a real lightweight API call."""
    from app.models.openai_provider import OpenAIProvider

    provider = OpenAIProvider(
        base_url=data.base_url,
        model_name=data.model_name,
        api_key=data.api_key,
        max_tokens=10,
    )
    try:
        # Actually call the API to verify connectivity with a minimal request
        response = await provider.chat(
            messages=[{"role": "user", "content": "Hi"}],
            temperature=0,
        )
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        model_id = response.get("model", data.model_name)
        return {"connected": True, "model": model_id, "response_preview": content[:50]}
    except Exception as e:
        return {"connected": False, "error": str(e)}
