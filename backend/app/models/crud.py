import logging
import os

from app.config import settings
from app.models.config import ModelConfig, ModelConfigs, RoleType
from app.models.database import get_connection

logger = logging.getLogger("app.models.crud")


def save_model_config(role: str, config: ModelConfig, enabled: bool = True, version: int = 1) -> None:
    """Save or update a model config for a given role. Preserves existing api_key if new one is 'existing' or empty."""
    conn = get_connection()
    try:
        # Ensure provider_type column exists (migration-safe)
        _ensure_provider_type_column(conn)

        conn.execute(
            """
            INSERT INTO model_configs (role, base_url, model_name, api_key, max_tokens, dimension, enabled, config_version, provider_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(role) DO UPDATE SET
                base_url = excluded.base_url,
                model_name = excluded.model_name,
                api_key = CASE WHEN excluded.api_key IN ('', 'existing') THEN model_configs.api_key ELSE excluded.api_key END,
                max_tokens = excluded.max_tokens,
                dimension = excluded.dimension,
                enabled = excluded.enabled,
                config_version = excluded.config_version,
                provider_type = excluded.provider_type,
                updated_at = CURRENT_TIMESTAMP
            """,
            (role, config.base_url, config.model_name, config.api_key,
             config.max_tokens, config.dimension, int(enabled), version,
             config.provider_type),
        )
        conn.commit()
    finally:
        conn.close()


def load_model_configs() -> ModelConfigs | None:
    """Load all model configs from database."""
    conn = get_connection()
    try:
        _ensure_provider_type_column(conn)

        cursor = conn.execute("SELECT * FROM model_configs")
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
                provider_type=row["provider_type"] if "provider_type" in row.keys() else "openai",
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


def _ensure_provider_type_column(conn) -> None:
    """Add provider_type column if it doesn't exist (migration-safe)."""
    try:
        cols = conn.execute("PRAGMA table_info(model_configs)").fetchall()
        col_names = [c[1] for c in cols]
        if "provider_type" not in col_names:
            conn.execute("ALTER TABLE model_configs ADD COLUMN provider_type TEXT DEFAULT 'openai'")
            conn.commit()
    except Exception:
        pass


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


def auto_configure_from_env() -> bool:
    """Auto-configure model settings from environment variables on first run.

    Checks for {ROLE}_BASE_URL, {ROLE}_MODEL_NAME, {ROLE}_API_KEY env vars.
    Returns True if any configuration was applied.
    """
    existing = load_model_configs()
    if existing is not None:
        return False

    configured = False
    for role in [r.value for r in RoleType]:
        prefix = role.upper()
        base_url = os.environ.get(f"{prefix}_BASE_URL", "")
        model_name = os.environ.get(f"{prefix}_MODEL_NAME", "")
        api_key = os.environ.get(f"{prefix}_API_KEY", "")

        if base_url and model_name:
            provider_type = os.environ.get(f"{prefix}_PROVIDER_TYPE", "openai")
            dimension = None
            dim_str = os.environ.get(f"{prefix}_DIMENSION", "")
            if dim_str:
                try:
                    dimension = int(dim_str)
                except ValueError:
                    pass

            config = ModelConfig(
                base_url=base_url,
                model_name=model_name,
                api_key=api_key,
                provider_type=provider_type,
                dimension=dimension,
            )
            save_model_config(role, config)
            configured = True
            logger.info("Auto-configured %s model from env: %s (%s)", role, model_name, provider_type)

    return configured
