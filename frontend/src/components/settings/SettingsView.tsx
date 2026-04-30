import { useState, useEffect } from 'react'
import { api } from '../../api/client'
import type { ModelConfigResponse } from '../../api/client'

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
}

const ROLES: ModelRole[] = [
  { key: 'main', label: '主模型', description: 'Agent 推理、L0/L1 编译', enabled: true, base_url: '', model_name: '', api_key: '', max_tokens: 8192 },
  { key: 'lightweight', label: '轻量模型', description: 'L1 段落摘要（可选）', enabled: false, base_url: '', model_name: '', api_key: '', max_tokens: 4096 },
  { key: 'embedding', label: 'Embedding', description: '向量检索（可选，未配置时使用关键词搜索）', enabled: false, base_url: '', model_name: '', api_key: '', max_tokens: 8192, dimension: 1024 },
  { key: 'vlm', label: '多模态 VLM', description: 'OCR 图片识别（可选）', enabled: false, base_url: '', model_name: '', api_key: '', max_tokens: 4096 },
]

export function Settings() {
  const [roles, setRoles] = useState<ModelRole[]>(ROLES)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ key: string; ok: boolean; msg: string } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadConfig()
  }, [])

  async function loadConfig() {
    try {
      const data = await api.getModelConfig()
      if (data.configured) {
        setRoles((prev) =>
          prev.map((r) => {
            const cfg = data[r.key as keyof ModelConfigResponse] as { base_url: string; model_name: string; max_tokens: number; dimension?: number; enabled?: boolean } | undefined
            return cfg
              ? { ...r, base_url: cfg.base_url, model_name: cfg.model_name, api_key: '', max_tokens: cfg.max_tokens, enabled: cfg.enabled ?? true, dimension: cfg.dimension ?? r.dimension }
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

  async function saveConfig(role: ModelRole) {
    try {
      const payload: Record<string, unknown> = {
        base_url: role.base_url,
        model_name: role.model_name,
        max_tokens: role.max_tokens,
        dimension: role.dimension,
        enabled: role.enabled,
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
      })
      setTestResult({ key: role.key, ok: result.connected, msg: result.error || `连接成功: ${result.model || role.model_name}` })
    } catch (e) {
      setTestResult({ key: role.key, ok: false, msg: String(e) })
    } finally {
      setTesting(null)
    }
  }

  if (loading) return <div className="text-stone-500">加载中...</div>

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold text-stone-800 dark:text-stone-100">系统设置</h2>

      {testResult && (
        <div
          className={`p-3 rounded-lg text-sm ${
            testResult.ok
              ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
              : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'
          }`}
        >
          {testResult.msg}
        </div>
      )}

      {roles.map((role) => (
        <div
          key={role.key}
          className="bg-white dark:bg-slate-800 rounded-xl border border-stone-200 dark:border-slate-700 p-5 space-y-4"
        >
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-stone-800 dark:text-stone-100">{role.label}</h3>
              <p className="text-xs text-stone-400 dark:text-stone-500">{role.description}</p>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={role.enabled}
                onChange={(e) => updateRole(role.key, 'enabled', e.target.checked)}
                className="accent-amber-600"
              />
              <span className="text-stone-500 dark:text-stone-400">启用</span>
            </label>
          </div>

          {role.enabled && (
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-stone-500 dark:text-stone-400 mb-1">Base URL</label>
                <input
                  type="text"
                  value={role.base_url}
                  onChange={(e) => updateRole(role.key, 'base_url', e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-stone-200 dark:border-slate-600 bg-stone-50 dark:bg-slate-700 text-stone-800 dark:text-stone-100 text-sm"
                  placeholder="https://api.openai.com/v1"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-stone-500 dark:text-stone-400 mb-1">Model Name</label>
                  <input
                    type="text"
                    value={role.model_name}
                    onChange={(e) => updateRole(role.key, 'model_name', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-stone-200 dark:border-slate-600 bg-stone-50 dark:bg-slate-700 text-stone-800 dark:text-stone-100 text-sm"
                    placeholder="gpt-4o"
                  />
                </div>
                <div>
                  <label className="block text-xs text-stone-500 dark:text-stone-400 mb-1">API Key</label>
                  <input
                    type="password"
                    value={role.api_key}
                    onChange={(e) => updateRole(role.key, 'api_key', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-stone-200 dark:border-slate-600 bg-stone-50 dark:bg-slate-700 text-stone-800 dark:text-stone-100 text-sm"
                    placeholder="sk-xxx"
                  />
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => saveConfig(role)}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm rounded-lg transition-colors"
                >
                  保存配置
                </button>
                <button
                  onClick={() => testConnection(role)}
                  disabled={testing === role.key}
                  className="px-4 py-2 bg-stone-200 dark:bg-slate-600 hover:bg-stone-300 dark:hover:bg-slate-500 text-stone-700 dark:text-stone-200 text-sm rounded-lg transition-colors disabled:opacity-50"
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
