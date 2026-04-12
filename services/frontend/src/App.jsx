import { useState } from 'react'
import PatientList  from './components/PatientList.jsx'
import EEGViewer    from './components/EEGViewer.jsx'
import InsightPanel from './components/InsightPanel.jsx'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function App() {
  const [selectedId, setSelectedId]     = useState(null)
  const [classifyData, setClassifyData] = useState(null)
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState(null)
  const [uploading, setUploading]       = useState(null)   // null | 'uploading' | 'staging'
  const [refreshToken, setRefreshToken] = useState(0)

  async function handleSelect(id) {
    if (id === selectedId) return
    setSelectedId(id)
    setClassifyData(null)
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/classify/${id}`)
      if (!res.ok) throw new Error(`API returned ${res.status}`)
      setClassifyData(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload(file) {
    setClassifyData(null)
    setSelectedId(null)
    setError(null)
    setUploading('uploading')
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${API}/classify/upload`, { method: 'POST', body: form })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `Upload failed (${res.status})`)
      }
      setUploading('staging')
      const data = await res.json()
      setClassifyData(data)
      setSelectedId(data.recording_id)
      setRefreshToken(t => t + 1)
    } catch (e) {
      setError(e.message)
    } finally {
      setUploading(null)
    }
  }

  const busy = loading || !!uploading

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden',
      fontFamily: 'system-ui, -apple-system, sans-serif', background: '#fff',
    }}>
      {/* ── top bar ── */}
      <header style={{
        height: 48, flexShrink: 0,
        display: 'flex', alignItems: 'center',
        padding: '0 20px',
        borderBottom: '1px solid #e0e0e0',
        background: '#fff',
      }}>
        <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: '-0.01em', color: '#212121' }}>
          Sleep Dashboard
        </span>
      </header>

      {/* ── body ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <PatientList
          apiBase={API}
          selectedId={selectedId}
          onSelect={handleSelect}
          onUpload={handleUpload}
          uploading={uploading}
          refreshToken={refreshToken}
        />

        <main style={{ flex: 1, overflowY: 'auto', background: '#fafafa' }}>
          {busy && (
            <div style={{ padding: 40, color: '#888', textAlign: 'center' }}>
              {uploading === 'staging'
                ? 'Running YASA sleep staging… this may take a few minutes for a full PSG.'
                : uploading
                ? 'Uploading file…'
                : 'Loading…'}
            </div>
          )}
          {error && (
            <div style={{ padding: 20, margin: 20, background: '#fff3f3',
                          border: '1px solid #ffcdd2', borderRadius: 6, color: '#c62828' }}>
              Error: {error}
            </div>
          )}
          {classifyData && !busy && (
            <>
              <EEGViewer    data={classifyData} />
              <InsightPanel data={classifyData} />
            </>
          )}
          {!classifyData && !busy && !error && (
            <div style={{ padding: 60, color: '#aaa', textAlign: 'center', fontSize: 15 }}>
              ← Select a recording to view analysis
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
