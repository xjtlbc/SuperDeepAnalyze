import { useState, useEffect } from 'react'
import { api } from '../../api/client'
import type { ModelConfigResponse, ProviderPreset } from '../../api/client'

interface ModelRole {
  key: string
  label: string
  description: string
  enabled: boolean
  base_url: string
  model_name: string
  api_key: string
  max_tokens: number
  dimension?: number
  provider_type: string
}

const ROLES: ModelRole[] = [
  { key: 'main', label: '主模型', description: 'Agent 推理、L0/L1 编译', enabled: true, base_url: '', model_name: '', api_key: '', max_tokens: 8192, provider_type: 'openai' },
  { key: 'lightweight', label: '轻量模型', description: 'L1 段落摘要（可选）', enabled: false, base_url: '', model_name: '', api_key: '', max_tokens: 4096, provider_type: 'openai' },
  { key: 'embedding', label: 'Embedding', description: '向量检索（可选，未配置时使用关键词搜索）', enabled: false, base_url: '', model_name: '', api_key: '', max_tokens: 8192, dimension: 1024, provider_type: 'openai' },
  { key: 'vlm', label: '多模态 VLM', description: 'OCR 图片识别（可选）', enabled: false, base_url: '', model_name: '', api_key: '', max_tokens: 4096, provider_type: 'openai' },
]

export function Settings() {
  const [roles, setRoles] = useState<ModelRole[]>(ROLES)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ key: string; ok: boolean; msg: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [presets, setPresets] = useState<ProviderPreset[]>([])
  const [activePresetRole, setActivePresetRole] = useState<string | null>(null)

  useEffect(() => {
    loadConfig()
    loadPresets()
  }, [])

  async function loadPresets() {
    try {
      const data = await api.getPresets()
      setPresets(data)
    } catch (e) {
      console.error('Failed to load presets:', e)
    }
  }

  async function loadConfig() {
    try {
      const data = await api.getModelConfig()
      if (data.configured) {
        setRoles((prev) =>
          prev.map((r) => {
            const cfg = data[r.key as keyof ModelConfigResponse] as { base_url: string; model_name: string; max_tokens: number; dimension?: number; enabled?: boolean; provider_type?: string } | undefined
            return cfg
              ? { ...r, base_url: cfg.base_url, model_name: cfg.model_name, api_key: '', max_tokens: cfg.max_tokens, enabled: cfg.enabled ?? true, dimension: cfg.dimension ?? r.dimension, provider_type: cfg.provider_type || 'openai' }
              : { ...r, enabled: false }
          })
        )
      }
    } catch (e) {
      console.error('Failed to load config:', e)
    } finally {
      setLoading(false)
    }
  }

  function updateRole(key: string, field: keyof ModelRole, value: unknown) {
    setRoles((prev) => prev.map((r) => (r.key === key ? { ...r, [field]: value } : r)))
  }

  function applyPreset(preset: ProviderPreset, roleKey: string) {
    updateRole(roleKey, 'base_url', preset.base_url)
    updateRole(roleKey, 'provider_type', preset.adapter)
    if (preset.models.length > 0) {
      updateRole(roleKey, 'model_name', preset.models[0].id)
    }
    setActivePresetRole(null)
  }

  async function saveConfig(role: ModelRole) {
    try {
      const payload: Record<string, unknown> = {
        base_url: role.base_url,
        model_name: role.model_name,
        max_tokens: role.max_tokens,
        dimension: role.dimension,
        enabled: role.enabled,
        provider_type: role.provider_type,
      }
      if (role.api_key && role.api_key !== 'existing') {
        payload.api_key = role.api_key
      }
      await api.updateModelConfig(role.key, payload)
      alert(`${role.label} 配置已保存`)
    } catch (e) {
      alert(`保存失败: ${e}`)
    }
  }

  async function testConnection(role: ModelRole) {
    setTesting(role.key)
    setTestResult(null)
    try {
      const result = await api.testConnection({
        base_url: role.base_url,
        model_name: role.model_name,
        api_key: role.api_key || 'test',
        provider_type: role.provider_type,
      })
      setTestResult({ key: role.key, ok: result.connected, msg: result.error || `连接成功: ${result.model || role.model_name}` })
    } catch (e) {
      setTestResult({ key: role.key, ok: false, msg: String(e) })
    } finally {
      setTesting(null)
    }
  }

  if (loading) return <div className="text-muted">加载中...</div>

  return (
    <div className="settings">
      <h2 className="settings__title">系统设置</h2>

      {testResult && (
        <div
          className={`settings__result ${testResult.ok ? 'settings__result--success' : 'settings__result--error'}`}
        >
          {testResult.msg}
        </div>
      )}

      {roles.map((role) => (
        <div
          key={role.key}
          className="settings__card"
        >
          <div className="settings__card-header">
            <div>
              <h3 className="settings__card-title">{role.label}</h3>
              <p className="settings__card-desc">{role.description}</p>
            </div>
            <label className="settings__toggle">
              <input
                type="checkbox"
                checked={role.enabled}
                onChange={(e) => updateRole(role.key, 'enabled', e.target.checked)}
                className="settings__toggle-checkbox"
              />
              <span className="settings__toggle-label">启用</span>
            </label>
          </div>

          {role.enabled && (
            <div className="settings__fields">
              {/* Provider type selector */}
              <div className="settings__provider-row">
                <label className="settings__field-label">协议：</label>
                <select
                  value={role.provider_type}
                  onChange={(e) => updateRole(role.key, 'provider_type', e.target.value)}
                  className="settings__select"
                >
                  <option value="openai">OpenAI 兼容</option>
                  <option value="anthropic">Anthropic</option>
                </select>
                <button
                  onClick={() => setActivePresetRole(activePresetRole === role.key ? null : role.key)}
                  className="settings__preset-toggle"
                >
                  {activePresetRole === role.key ? '收起预设' : '快速配置'}
                </button>
              </div>

              {/* Provider preset grid */}
              {activePresetRole === role.key && presets.length > 0 && (
                <div className="settings__preset-grid">
                  {presets.map((preset) => (
                    <button
                      key={preset.id}
                      onClick={() => applyPreset(preset, role.key)}
                      className={`settings__preset-item ${
                        preset.adapter !== role.provider_type
                          ? 'settings__preset-item--disabled'
                          : ''
                      } ${preset.is_local ? 'settings__preset-item--local' : ''}`}
                      disabled={preset.adapter !== role.provider_type}
                      title={preset.is_local ? `${preset.name} (本地)` : preset.name}
                    >
                      <span className="settings__preset-name">{preset.name}</span>
                      {preset.is_local && <span className="settings__preset-local-badge">本地</span>}
                    </button>
                  ))}
                </div>
              )}

              {/* Model selection dropdown when preset has models */}
              <div>
                <label className="settings__field-label settings__field-label--block">Base URL</label>
                <input
                  type="text"
                  value={role.base_url}
                  onChange={(e) => updateRole(role.key, 'base_url', e.target.value)}
                  className="settings__input"
                  placeholder="https://api.openai.com/v1"
                />
              </div>
              <div className="settings__row-2col">
                <div>
                  <label className="settings__field-label settings__field-label--block">Model Name</label>
                  <input
                    type="text"
                    value={role.model_name}
                    onChange={(e) => updateRole(role.key, 'model_name', e.target.value)}
                    className="settings__input"
                    placeholder="gpt-4o"
                  />
                </div>
                <div>
                  <label className="settings__field-label settings__field-label--block">API Key</label>
                  <input
                    type="password"
                    value={role.api_key}
                    onChange={(e) => updateRole(role.key, 'api_key', e.target.value)}
                    className="settings__input"
                    placeholder="sk-xxx"
                  />
                </div>
              </div>
              <div className="settings__actions">
                <button
                  onClick={() => saveConfig(role)}
                  className="settings__btn-save"
                >
                  保存配置
                </button>
                <button
                  onClick={() => testConnection(role)}
                  disabled={testing === role.key}
                  className="settings__btn-test"
                >
                  {testing === role.key ? '测试中...' : '测试连接'}
                </button>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
