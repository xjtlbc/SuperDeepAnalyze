const API_BASE = import.meta.env.VITE_API_BASE || '';

interface FetchOptions extends RequestInit {
  params?: Record<string, string>;
}

async function request<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { params, ...fetchOptions } = options;

  let url = `${API_BASE}${path}`;
  if (params) {
    const qs = new URLSearchParams(params).toString();
    url += `?${qs}`;
  }

  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Accept': 'application/json', 'Accept-Charset': 'utf-8' },
    ...fetchOptions,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: response.statusText }));
    throw new Error(error.message || `HTTP ${response.status}`);
  }

  return response.json();
}

export interface ModelConfigResponse {
  configured: boolean;
  main?: { base_url: string; model_name: string; max_tokens: number; dimension?: number; provider_type?: string };
  lightweight?: { base_url: string; model_name: string; max_tokens: number; dimension?: number; provider_type?: string };
  embedding?: { base_url: string; model_name: string; max_tokens: number; dimension?: number; provider_type?: string };
  vlm?: { base_url: string; model_name: string; max_tokens: number; dimension?: number; provider_type?: string };
}

interface TestConnectionResponse {
  connected: boolean;
  error?: string;
  model?: string;
  response_preview?: string;
}

export interface ProviderPreset {
  id: string
  name: string
  adapter: string
  base_url: string
  is_local: boolean
  features: string[]
  models: Array<{
    id: string
    name: string
    context_window: number
    supports_tools: boolean
    supports_vision: boolean
  }>
}

export const api = {
  health: () => request<{ status: string; version: string }>('/api/health'),
  getModelConfig: () => request<ModelConfigResponse>('/api/models/config'),
  updateModelConfig: (role: string, data: Record<string, unknown>) =>
    request(`/api/models/config/${role}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  testConnection: (data: { base_url: string; model_name: string; api_key: string; provider_type?: string }) =>
    request<TestConnectionResponse>('/api/models/test-connection', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getPresets: () => request<ProviderPreset[]>('/api/models/presets'),
};
