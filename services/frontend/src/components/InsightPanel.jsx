function zColor(z) {
  const a = Math.abs(z)
  if (a >= 8)  return '#b71c1c'
  if (a >= 4)  return '#c62828'
  if (a >= 2)  return '#e65100'
  return '#2e7d32'
}

function ZBadge({ z }) {
  return (
    <span style={{
      display: 'inline-block', fontSize: 11, fontWeight: 700,
      padding: '2px 8px', borderRadius: 4,
      background: zColor(z), color: 'white',
      minWidth: 52, textAlign: 'center',
    }}>
      z {z > 0 ? '+' : ''}{z}
    </span>
  )
}

function AnomalyCard({ anomaly }) {
  const { label, value, normal_mean, normal_std, z_score, direction } = anomaly
  const c = zColor(z_score)
  return (
    <div style={{
      padding: '12px 14px', borderRadius: 8,
      border: `1px solid ${c}40`,
      background: `${c}0a`,
      marginBottom: 10,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', marginBottom: 5 }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: '#212121' }}>{label}</span>
        <ZBadge z={z_score} />
      </div>
      <div style={{ fontSize: 12, color: '#555' }}>
        Measured&nbsp;<b>{value}</b>&nbsp;
        <span style={{ color: '#888' }}>
          (norm {normal_mean} ± {normal_std} — {direction})
        </span>
      </div>
    </div>
  )
}

export default function InsightPanel({ data, onConfigureKey }) {
  const { anomalies = [], narrative, narrative_cached, pathology } = data
  const noKey = narrative?.startsWith('Narrative unavailable')

  return (
    <section style={{ background: 'white', margin: '0 16px 16px',
                      borderRadius: 10, border: '1px solid #e0e0e0',
                      padding: 20 }}>

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>

        {/* ── anomalies column ── */}
        <div style={{ flex: '0 0 320px' }}>
          <h3 style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase',
                       letterSpacing: '0.05em', color: '#555', marginBottom: 14 }}>
            Top Anomalies vs. AASM Norms
          </h3>
          {anomalies.length === 0
            ? <p style={{ color: '#aaa', fontSize: 13 }}>No anomalies detected.</p>
            : anomalies.map((a, i) => <AnomalyCard key={i} anomaly={a} />)
          }
        </div>

        {/* ── narrative column ── */}
        <div style={{ flex: 1, minWidth: 280 }}>
          <h3 style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase',
                       letterSpacing: '0.05em', color: '#555', marginBottom: 14,
                       display: 'flex', alignItems: 'center', gap: 8 }}>
            Clinical Narrative
            {narrative_cached && (
              <span style={{ fontSize: 10, fontWeight: 500, color: '#aaa',
                             textTransform: 'none', letterSpacing: 0 }}>
                (cached)
              </span>
            )}
          </h3>

          {noKey ? (
            <div style={{ padding: '14px 16px', borderRadius: 8,
                          background: '#f5f5f5', border: '1px solid #e0e0e0',
                          fontSize: 13, color: '#aaa', fontStyle: 'italic' }}>
              {narrative}
              <div style={{ marginTop: 10, fontStyle: 'normal', display: 'flex', alignItems: 'center', gap: 8 }}>
                <button
                  onClick={onConfigureKey}
                  style={{
                    padding: '5px 14px', borderRadius: 6, border: 'none',
                    background: '#1976d2', color: 'white', fontSize: 12,
                    fontWeight: 600, cursor: 'pointer',
                  }}
                >
                  Set API key
                </button>
                <span style={{ color: '#aaa', fontSize: 12 }}>to enable AI-generated clinical summaries</span>
              </div>
            </div>
          ) : (
            <div style={{ padding: '16px 18px', borderRadius: 8,
                          background: '#f8f9fa', border: '1px solid #e8e8e8',
                          fontSize: 14, lineHeight: 1.7, color: '#212121' }}>
              {narrative}
            </div>
          )}

          {/* pathology context pill */}
          <div style={{ marginTop: 14, fontSize: 12, color: '#888' }}>
            Pathology context:&nbsp;
            <span style={{ fontWeight: 600, color: '#1565c0' }}>{pathology}</span>
            &nbsp;· Anomaly scores derived from YASA feature set vs. AASM adult reference norms
          </div>
        </div>

      </div>
    </section>
  )
}
