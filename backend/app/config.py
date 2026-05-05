from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
    DATA_DIR: Path = PROJECT_ROOT / "data"
    SQLITE_PATH: Path = DATA_DIR / "sqlite.db"
    FAISS_DIR: Path = DATA_DIR / "faiss"
    KB_DIR: Path = DATA_DIR / "knowledge_bases"

    API_PREFIX: str = "/api"
    agent_max_iterations: int = 50
    agent_max_wall_seconds: int = 180
    agent_reflection_interval: int = 3
    agent_confidence_threshold: float = 0.80
    agent_iteration_budget_simple: int = 5
    agent_iteration_budget_complex: int = 20
    agent_session_notes_interval: int = 8
    agent_cache_edit_threshold: float = 0.70
    rrf_k: int = 60
    parse_timeout_seconds: int = 600
    docling_timeout_seconds: int = 180

    class Config:
        env_file = ".env"


class FeatureFlags(BaseSettings):
    """Runtime feature toggles. Priority: env var > settings > defaults.
    Env var format: DA_<FLAG_NAME> (e.g. DA_STREAMING_TOOLS=false)
    """
    # Agent features
    agent_streaming_tool_execution: bool = True
    agent_orchestrator: bool = True
    agent_5layer_compression: bool = True
    agent_structured_memory: bool = True

    # Compilation features
    compile_contradiction_detection: bool = True
    compile_timeline_builder: bool = True
    compile_abstract_enhancement: bool = True

    class Config:
        env_file = ".env"
        env_prefix = "DA_"


settings = Settings()
flags = FeatureFlags()
