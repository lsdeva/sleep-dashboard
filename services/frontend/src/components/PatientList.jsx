import { useEffect, useRef, useState } from 'react'

const PATH_BADGE = {
  Normal:                             { bg: '#e8f5e9', color: '#2e7d32' },
  Insomnia:                           { bg: '#e3f2fd', color: '#1565c0' },
  'REM Behavior Disorder':            { bg: '#fce4ec', color: '#880e4f' },
  'Nocturnal Frontal Lobe Epilepsy':  { bg: '#fff3e0', color: '#e65100' },
  'Periodic Leg Movements':           { bg: '#f3e5f5', color: '#6a1b9a' },
  'Sleep-Disordered Breathing':       { bg: '#e0f7fa', color: '#006064' },
  Bruxism:                            { bg: '#fafafa', color: '#424242' },
  Narcolepsy:                         { bg: '#fff8e1', color: '#f57f17' },
}

export default function PatientList({ apiBase, selectedId, onSelect, onUpload, uploading, refreshToken }) {
  const [patients, setPatients] = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const fileInputRef            = useRef(null)

  useEffect(() => {
    setLoading(true)
    fetch(`${apiBase}/patients`)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(data => { setPatients(data); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [apiBase, refreshToken])

  function handleFileChange(e) {
    const file = e.target.files?.[0]
    if (file) {
      onUpload(file)
      e.target.value = ''   // reset so same file can be re-selected
    }
  }

  return (
    <aside style={{
      width: 260, flexShrink: 0,
      borderRight: '1px solid #e0e0e0',
      background: '#f5f5f5',
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden',
    }}>
      {/* header */}
      <div style={{ padding: '10px 12px', borderBottom: '1px solid #e0e0e0',
                    background: '#efefef', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ fontWeight: 700, fontSize: 13, letterSpacing: '0.04em',
                      color: '#333', textTransform: 'uppercase' }}>
          Recordings {patients.length > 0 && `(${patients.length})`}
        </div>

        {/* upload button */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".edf"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
        <button
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
          style={{
            width: '100%', padding: '7px 0',
            borderRadius: 6, border: '1px dashed #bbb',
            background: uploading ? '#f5f5f5' : 'white',
            color: uploading ? '#aaa' : '#1976d2',
            fontSize: 12, fontWeight: 600, cursor: uploading ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
          }}
        >
          {uploading ? (
            <>
              <Spinner />
              {uploading === 'staging' ? 'Running YASA…' : 'Uploading…'}
            </>
          ) : (
            <>+ Upload EDF</>
          )}
        </button>
      </div>

      <div style={{ overflowY: 'auto', flex: 1 }}>
        {loading && !uploading && (
          <div style={{ padding: 16, color: '#999', fontSize: 13 }}>Loading…</div>
        )}
        {error && (
          <div style={{ padding: 16, color: '#c62828', fontSize: 13 }}>Error: {error}</div>
        )}
        {patients.map(p => {
          const badge  = PATH_BADGE[p.pathology] || { bg: '#f5f5f5', color: '#555' }
          const active = p.recording_id === selectedId
          const effOk  = p.sleep_efficiency_pct >= 80

          return (
            <div
              key={p.recording_id}
              onClick={() => onSelect(p.recording_id)}
              style={{
                padding: '11px 14px',
                cursor: 'pointer',
                borderBottom: '1px solid #e8e8e8',
                borderLeft: active ? '3px solid #1976d2' : '3px solid transparent',
                background: active ? '#e3f2fd' : 'white',
                transition: 'background 0.1s',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between',
                            alignItems: 'center', marginBottom: 4 }}>
                <span style={{ fontWeight: 700, fontSize: 14,
                               color: active ? '#1565c0' : '#212121' }}>
                  {p.recording_id.toUpperCase()}
                </span>
                <span style={{
                  fontSize: 11, fontWeight: 600,
                  padding: '1px 6px', borderRadius: 10,
                  background: effOk ? '#e8f5e9' : '#fff3e0',
                  color: effOk ? '#2e7d32' : '#e65100',
                }}>
                  {p.sleep_efficiency_pct?.toFixed(0)}%
                </span>
              </div>
              <div style={{
                display: 'inline-block', fontSize: 11, padding: '1px 7px',
                borderRadius: 10, background: badge.bg, color: badge.color,
                fontWeight: 500, marginBottom: 4,
              }}>
                {p.pathology}
              </div>
              <div style={{ fontSize: 11, color: '#888' }}>
                TST {p.tst_minutes?.toFixed(0)}′ · {p.n_epochs} epochs
              </div>
            </div>
          )
        })}
      </div>
    </aside>
  )
}

function Spinner() {
  return (
    <span style={{
      display: 'inline-block', width: 10, height: 10,
      border: '2px solid #ccc', borderTopColor: '#1976d2',
      borderRadius: '50%', animation: 'spin 0.7s linear infinite',
    }} />
  )
}
