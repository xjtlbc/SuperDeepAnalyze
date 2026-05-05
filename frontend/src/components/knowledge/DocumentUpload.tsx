import { useState, useRef, useCallback } from 'react'
import { Upload, File, X } from 'lucide-react'

interface UploadFile {
  file: globalThis.File
  progress: number
  status: 'pending' | 'uploading' | 'done' | 'error'
  error?: string
}

export function DocumentUpload({ kbId, onUploaded }: { kbId: string; onUploaded?: () => void }) {
  const [files, setFiles] = useState<UploadFile[]>([])
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const uploadFile = useCallback(async (uf: UploadFile, idx: number) => {
    setFiles(prev => prev.map((f, i) => i === idx ? { ...f, status: 'uploading' as const } : f))

    const form = new FormData()
    form.append('file', uf.file)

    try {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `/api/documents/upload/${kbId}`)
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 100)
          setFiles(prev => prev.map((f, i) => i === idx ? { ...f, progress: pct } : f))
        }
      }

      await new Promise<void>((resolve, reject) => {
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) resolve()
          else reject(new Error(`HTTP ${xhr.status}`))
        }
        xhr.onerror = () => reject(new Error('网络错误'))
        xhr.send(form)
      })

      setFiles(prev => prev.map((f, i) => i === idx ? { ...f, status: 'done' as const, progress: 100 } : f))
      onUploaded?.()
    } catch (err: any) {
      setFiles(prev => prev.map((f, i) => i === idx ? { ...f, status: 'error' as const, error: err.message } : f))
    }
  }, [kbId, onUploaded])

  const addFiles = useCallback((newFiles: FileList | null) => {
    if (!newFiles) return
    const toAdd: UploadFile[] = []
    for (let i = 0; i < newFiles.length; i++) {
      toAdd.push({ file: newFiles[i], progress: 0, status: 'pending' })
    }
    setFiles(prev => {
      const combined = [...prev, ...toAdd]
      combined.forEach((f, i) => {
        if (f.status === 'pending') uploadFile(f, i)
      })
      return combined
    })
  }, [uploadFile])

  const removeFile = (idx: number) => {
    setFiles(prev => prev.filter((_, i) => i !== idx))
  }

  const getTypeIcon = (name: string) => {
    const ext = name.split('.').pop()?.toLowerCase()
    const colors: Record<string, string> = {
      pdf: '#e03131', doc: '#1c7ed6', docx: '#1c7ed6',
      xls: '#2f9e44', xlsx: '#2f9e44', csv: '#2f9e44',
      txt: '#868e96', md: '#868e96',
    }
    return (
      <File size={20} color={colors[ext || ''] || 'var(--text-muted)'} />
    )
  }

  return (
    <div>
      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files) }}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${dragging ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: 12,
          padding: '32px 16px',
          textAlign: 'center',
          cursor: 'pointer',
          background: dragging ? 'var(--accent-subtle)' : 'var(--bg-secondary)',
          transition: 'background 0.15s ease, border-color 0.15s ease',
        }}
      >
        <Upload size={28} color="var(--text-muted)" style={{ margin: '0 auto 8px', display: 'block' }} />
        <p style={{ fontSize: 13, fontWeight: 500, margin: '0 0 4px', color: 'var(--text)' }}>
          拖拽文件到此处上传
        </p>
        <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: 0 }}>
          支持 PDF / Word (.doc/.docx) / Excel (.xls/.xlsx) / TXT
        </p>
      </div>
      <input ref={inputRef} type="file" multiple onChange={e => addFiles(e.target.files)} style={{ display: 'none' }}
        accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md" />

      {/* File list */}
      {files.length > 0 && (
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {files.map((uf, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '8px 12px', borderRadius: 8,
              background: 'var(--bg-secondary)', border: '1px solid var(--border)',
            }}>
              {getTypeIcon(uf.file.name)}
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontSize: 12, margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {uf.file.name}
                </p>
                {uf.status === 'uploading' && (
                  <div style={{ height: 3, background: 'var(--bg-tertiary)', borderRadius: 2, marginTop: 4, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${uf.progress}%`, background: 'var(--accent)', borderRadius: 2, transition: 'width 0.3s ease' }} />
                  </div>
                )}
              </div>
              {(uf.status === 'done' || uf.status === 'error') && (
                <button onClick={() => removeFile(i)} style={{ padding: 2, cursor: 'pointer', background: 'none', border: 'none' }}>
                  <X size={14} color={uf.status === 'error' ? 'var(--error)' : 'var(--text-muted)'} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
