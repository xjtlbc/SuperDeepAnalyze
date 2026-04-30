from app.config import settings
from app.models.config import ModelConfig, ModelConfigs, RoleType
from app.models.database import get_connection


def save_model_config(role: str, config: ModelConfig, enabled: bool = True, version: int = 1) -> None:
    """Save or update a model config for a given role. Preserves existing api_key if new one is 'existing' or empty."""
    conn = get_connection()
    try:
        # First try to insert; on conflict, update all fields (preserving api_key if placeholder)
        conn.execute(
            """
            INSERT INTO model_configs (role, base_url, model_name, api_key, max_tokens, dimension, enabled, config_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(role) DO UPDATE SET
                base_url = excluded.base_url,
                model_name = excluded.model_name,
                api_key = CASE WHEN excluded.api_key IN ('', 'existing') THEN model_configs.api_key ELSE excluded.api_key END,
                max_tokens = excluded.max_tokens,
                dimension = excluded.dimension,
                enabled = excluded.enabled,
                config_version = excluded.config_version,
                updated_at = CURRENT_TIMESTAMP
            """,
            (role, config.base_url, config.model_name, config.api_key,
             config.max_tokens, config.dimension, int(enabled), version),
        )
        conn.commit()
    finally:
        conn.close()


def load_model_configs() -> ModelConfigs | None:
    """Load all model configs from database."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM model_configs"
        )
        rows = cursor.fetchall()

        if not rows:
            return None

        configs: dict = {}
        rrf_k = settings.rrf_k
        agent_max_iterations = settings.agent_max_iterations

        for row in rows:
            role = row["role"]
            mc = ModelConfig(
                base_url=row["base_url"],
                model_name=row["model_name"],
                api_key=row["api_key"],
                max_tokens=row["max_tokens"],
                dimension=row["dimension"],
            )
            configs[role] = mc

        if "main" not in configs:
            return None

        return ModelConfigs(
            main=configs["main"],
            lightweight=configs.get("lightweight"),
            embedding=configs.get("embedding"),
            vlm=configs.get("vlm"),
            rrf_k=rrf_k,
            agent_max_iterations=agent_max_iterations,
        )
    finally:
        conn.close()


def bump_config_version() -> int:
    """Bump all config versions and return the new version."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT MAX(config_version) as max_ver FROM model_configs"
        )
        row = cursor.fetchone()
        new_version = (row["max_ver"] or 0) + 1

        conn.execute(
            "UPDATE model_configs SET config_version = ?, updated_at = CURRENT_TIMESTAMP",
            (new_version,),
        )
        conn.commit()
        return new_version
    finally:
        conn.close()
