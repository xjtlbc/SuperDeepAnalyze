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
    rrf_k: int = 60
    parse_timeout_seconds: int = 600
    docling_timeout_seconds: int = 180

    class Config:
        env_file = ".env"


settings = Settings()
