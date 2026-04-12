import { useState } from 'react'

export default function ApiKeyModal({ onSave, onSkip }) {
  const [key, setKey]     = useState('')
  const [error, setError] = useState('')

  function handleSave() {
    const trimmed = key.trim()
    if (!trimmed) { setError('Please enter a key.'); return }
    if (!trimmed.startsWith('sk-ant-')) {
      setError('Anthropic keys start with sk-ant-')
      return
    }
    setError('')
    onSave(trimmed)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') handleSave()
    if (e.key === 'Escape') onSkip()
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'white', borderRadius: 12, padding: '32px 36px',
        width: 440, boxShadow: '0 8px 40px rgba(0,0,0,0.18)',
      }}>
        {/* header */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#212121', marginBottom: 6 }}>
            Anthropic API Key
          </div>
          <div style={{ fontSize: 13, color: '#666', lineHeight: 1.5 }}>
            Required for AI-generated clinical narratives. The key is stored only in
            your browser (localStorage) and sent directly to this app's backend —
            never to any third-party service.
          </div>
        </div>

        {/* input */}
        <input
          autoFocus
          type="password"
          placeholder="sk-ant-api03-…"
          value={key}
          onChange={e => { setKey(e.target.value); setError('') }}
          onKeyDown={handleKeyDown}
          style={{
            width: '100%', padding: '10px 12px', fontSize: 13,
            border: `1px solid ${error ? '#ef5350' : '#ccc'}`,
            borderRadius: 6, outline: 'none', boxSizing: 'border-box',
            fontFamily: 'monospace',
          }}
        />
        {error && (
          <div style={{ marginTop: 5, fontSize: 12, color: '#c62828' }}>{error}</div>
        )}

        {/* actions */}
        <div style={{ display: 'flex', gap: 10, marginTop: 20, justifyContent: 'flex-end' }}>
          <button
            onClick={onSkip}
            style={{
              padding: '8px 18px', borderRadius: 6, border: '1px solid #ddd',
              background: 'white', fontSize: 13, cursor: 'pointer', color: '#555',
            }}
          >
            Skip
          </button>
          <button
            onClick={handleSave}
            style={{
              padding: '8px 20px', borderRadius: 6, border: 'none',
              background: '#1976d2', color: 'white', fontSize: 13,
              fontWeight: 600, cursor: 'pointer',
            }}
          >
            Save key
          </button>
        </div>

        {/* footnote */}
        <div style={{ marginTop: 16, fontSize: 11, color: '#aaa' }}>
          Get a key at{' '}
          <a
            href="https://console.anthropic.com/settings/keys"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#1976d2' }}
          >
            console.anthropic.com
          </a>
          . Skipping disables the narrative panel.
        </div>
      </div>
    </div>
  )
}
