from enum import Enum
from pydantic import BaseModel, Field


class RoleType(str, Enum):
    MAIN = "main"
    LIGHTWEIGHT = "lightweight"
    EMBEDDING = "embedding"
    VLM = "vlm"


class ModelConfig(BaseModel):
    base_url: str
    model_name: str
    api_key: str = Field(default="", repr=False)
    max_tokens: int = 8192
    dimension: int | None = None

    def model_dump_safe(self) -> dict:
        """Dump without api_key for logging/display."""
        d = self.model_dump()
        d["api_key"] = "***" if d["api_key"] else ""
        return d


class ModelConfigs(BaseModel):
    main: ModelConfig
    lightweight: ModelConfig | None = None
    embedding: ModelConfig | None = None
    vlm: ModelConfig | None = None
    rrf_k: int = 60
    agent_max_iterations: int = 50

    def get_model(self, role: RoleType) -> ModelConfig:
        match role:
            case RoleType.MAIN:
                return self.main
            case RoleType.LIGHTWEIGHT:
                return self.lightweight or self.main
            case RoleType.EMBEDDING:
                if self.embedding is None:
                    raise ValueError("Embedding model not configured")
                return self.embedding
            case RoleType.VLM:
                if self.vlm is None:
                    raise ValueError("VLM model not configured")
                return self.vlm
