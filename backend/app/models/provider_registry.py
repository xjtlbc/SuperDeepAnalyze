"""Provider registry: catalog of LLM provider presets."""

from dataclasses import dataclass, field


@dataclass
class ModelMeta:
    id: str
    name: str
    context_window: int = 4096
    max_output_tokens: int = 4096
    supports_tools: bool = True
    supports_vision: bool = False


@dataclass
class ProviderPreset:
    id: str
    name: str
    adapter: str  # "openai" or "anthropic"
    base_url: str
    base_url_cn: str | None = None
    models: list[ModelMeta] = field(default_factory=list)
    features: list[str] = field(default_factory=lambda: ["chat"])
    is_local: bool = False
    api_key_env_var: str | None = None


PROVIDER_REGISTRY: dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        id="openai", name="OpenAI", adapter="openai",
        base_url="https://api.openai.com/v1",
        api_key_env_var="OPENAI_API_KEY",
        features=["chat", "embedding", "vision"],
        models=[
            ModelMeta("gpt-4o", "GPT-4o", 128000, 16384, True, True),
            ModelMeta("gpt-4o-mini", "GPT-4o Mini", 128000, 16384, True, False),
            ModelMeta("text-embedding-3-small", "Embedding 3 Small", 8191, 0, False, False),
        ],
    ),
    "anthropic": ProviderPreset(
        id="anthropic", name="Anthropic (Claude)", adapter="anthropic",
        base_url="https://api.anthropic.com",
        api_key_env_var="ANTHROPIC_API_KEY",
        features=["chat", "vision"],
        models=[
            ModelMeta("claude-sonnet-4-20250514", "Claude Sonnet 4", 200000, 8192, True, True),
            ModelMeta("claude-haiku-4-20250514", "Claude Haiku 4", 200000, 8192, True, True),
        ],
    ),
    "deepseek": ProviderPreset(
        id="deepseek", name="DeepSeek", adapter="openai",
        base_url="https://api.deepseek.com/v1",
        api_key_env_var="DEEPSEEK_API_KEY",
        features=["chat", "embedding"],
        models=[
            ModelMeta("deepseek-chat", "DeepSeek Chat", 131072, 8192, True, False),
            ModelMeta("deepseek-reasoner", "DeepSeek Reasoner", 131072, 8192, True, False),
        ],
    ),
    "qwen": ProviderPreset(
        id="qwen", name="通义千问 (Qwen)", adapter="openai",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        base_url_cn="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env_var="DASHSCOPE_API_KEY",
        features=["chat", "embedding", "vision"],
        models=[
            ModelMeta("qwen-plus", "Qwen Plus", 131072, 8192, True, False),
            ModelMeta("qwen-turbo", "Qwen Turbo", 131072, 8192, True, False),
            ModelMeta("text-embedding-v3", "Embedding V3", 8192, 0, False, False),
        ],
    ),
    "moonshot": ProviderPreset(
        id="moonshot", name="Moonshot (Kimi)", adapter="openai",
        base_url="https://api.moonshot.cn/v1",
        api_key_env_var="MOONSHOT_API_KEY",
        features=["chat"],
        models=[ModelMeta("moonshot-v1-128k", "Moonshot V1 128K", 131072, 8192, True, False)],
    ),
    "zhipu": ProviderPreset(
        id="zhipu", name="智谱 GLM", adapter="openai",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_env_var="ZHIPU_API_KEY",
        features=["chat", "embedding"],
        models=[
            ModelMeta("glm-4-plus", "GLM-4 Plus", 131072, 8192, True, False),
            ModelMeta("embedding-3", "Embedding 3", 8192, 0, False, False),
        ],
    ),
    "doubao": ProviderPreset(
        id="doubao", name="字节豆包", adapter="openai",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key_env_var="DOUBAO_API_KEY",
        features=["chat", "embedding"],
        models=[ModelMeta("doubao-pro-128k", "豆包 Pro 128K", 131072, 8192, True, False)],
    ),
    "minimax": ProviderPreset(
        id="minimax", name="MiniMax", adapter="openai",
        base_url="https://api.minimax.chat/v1",
        api_key_env_var="MINIMAX_API_KEY",
        features=["chat"],
        models=[ModelMeta("MiniMax-Text-01", "MiniMax Text 01", 131072, 8192, True, False)],
    ),
    "hunyuan": ProviderPreset(
        id="hunyuan", name="腾讯混元", adapter="openai",
        base_url="https://api.hunyuan.cloud.tencent.com/v1",
        api_key_env_var="HUNYUAN_API_KEY",
        features=["chat"],
        models=[ModelMeta("hunyuan-turbo", "混元 Turbo", 131072, 8192, True, False)],
    ),
    "yi": ProviderPreset(
        id="yi", name="01.AI (Yi)", adapter="openai",
        base_url="https://api.lingyiwanwu.com/v1",
        api_key_env_var="YI_API_KEY",
        features=["chat"],
        models=[ModelMeta("yi-large", "Yi Large", 16384, 4096, True, False)],
    ),
    "baichuan": ProviderPreset(
        id="baichuan", name="百川", adapter="openai",
        base_url="https://api.baichuan-ai.com/v1",
        api_key_env_var="BAICHUAN_API_KEY",
        features=["chat"],
        models=[ModelMeta("Baichuan4", "Baichuan 4", 192000, 8192, True, False)],
    ),
    "siliconflow": ProviderPreset(
        id="siliconflow", name="SiliconFlow", adapter="openai",
        base_url="https://api.siliconflow.cn/v1",
        api_key_env_var="SILICONFLOW_API_KEY",
        features=["chat", "embedding"],
        models=[ModelMeta("Qwen/Qwen2.5-72B-Instruct", "Qwen2.5 72B", 32768, 8192, True, False)],
    ),
    "groq": ProviderPreset(
        id="groq", name="Groq", adapter="openai",
        base_url="https://api.groq.com/openai/v1",
        api_key_env_var="GROQ_API_KEY",
        features=["chat"],
        models=[ModelMeta("llama-3.3-70b-versatile", "Llama 3.3 70B", 131072, 8192, True, False)],
    ),
    "mistral": ProviderPreset(
        id="mistral", name="Mistral", adapter="openai",
        base_url="https://api.mistral.ai/v1",
        api_key_env_var="MISTRAL_API_KEY",
        features=["chat", "embedding"],
        models=[ModelMeta("mistral-large-latest", "Mistral Large", 131072, 8192, True, False)],
    ),
    "gemini": ProviderPreset(
        id="gemini", name="Google Gemini", adapter="openai",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env_var="GOOGLE_API_KEY",
        features=["chat", "embedding", "vision"],
        models=[ModelMeta("gemini-2.0-flash", "Gemini 2.0 Flash", 1048576, 8192, True, True)],
    ),
    "openrouter": ProviderPreset(
        id="openrouter", name="OpenRouter", adapter="openai",
        base_url="https://openrouter.ai/api/v1",
        api_key_env_var="OPENROUTER_API_KEY",
        features=["chat", "vision"],
        models=[ModelMeta("anthropic/claude-sonnet-4-20250514", "Claude Sonnet 4", 200000, 8192, True, True)],
    ),
    "ollama": ProviderPreset(
        id="ollama", name="Ollama", adapter="openai",
        base_url="http://localhost:11434/v1",
        is_local=True,
        features=["chat", "embedding"],
        models=[],
    ),
    "vllm": ProviderPreset(
        id="vllm", name="vLLM", adapter="openai",
        base_url="http://localhost:8000/v1",
        is_local=True,
        features=["chat", "embedding"],
        models=[],
    ),
    "lm_studio": ProviderPreset(
        id="lm_studio", name="LM Studio", adapter="openai",
        base_url="http://localhost:1234/v1",
        is_local=True,
        features=["chat", "embedding"],
        models=[],
    ),
    "custom_openai": ProviderPreset(
        id="custom_openai", name="自定义 (OpenAI兼容)", adapter="openai",
        base_url="",
        features=["chat"],
        models=[],
    ),
    "custom_anthropic": ProviderPreset(
        id="custom_anthropic", name="自定义 (Anthropic兼容)", adapter="anthropic",
        base_url="",
        features=["chat"],
        models=[],
    ),
    "newapi": ProviderPreset(
        id="newapi", name="NewAPI / OneAPI", adapter="openai",
        base_url="http://localhost:3000/v1",
        features=["chat", "embedding", "vision"],
        models=[],
    ),
}


def get_all_presets() -> list[ProviderPreset]:
    return list(PROVIDER_REGISTRY.values())


def get_preset(provider_id: str) -> ProviderPreset | None:
    return PROVIDER_REGISTRY.get(provider_id)


def get_preset_ids() -> list[str]:
    return list(PROVIDER_REGISTRY.keys())
