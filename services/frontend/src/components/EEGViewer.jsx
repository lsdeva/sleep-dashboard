import createPlotlyComponent from 'react-plotly.js/factory'
const Plot = createPlotlyComponent(window.Plotly)

const STAGE_COLOR = { W: '#ef5350', N1: '#ffa726', N2: '#42a5f5', N3: '#1a237e', R: '#ab47bc' }
const STAGE_LABEL = { W: 'Wake', N1: 'N1 Light', N2: 'N2 Core', N3: 'N3 Deep', R: 'REM' }

function MetricCard({ label, value, warn }) {
  return (
    <div style={{
      background: warn ? '#fff8e1' : 'white',
      border: `1px solid ${warn ? '#ffe082' : '#e0e0e0'}`,
      borderRadius: 8, padding: '10px 14px',
    }}>
      <div style={{ fontSize: 10, color: '#888', textTransform: 'uppercase',
                    letterSpacing: '0.05em', marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 700,
                    color: warn ? '#e65100' : '#212121' }}>{value ?? '—'}</div>
    </div>
  )
}

export default function EEGViewer({ data }) {
  const dist = data.stage_distribution   // { W, N1, N2, N3, R }
  const keys = Object.keys(dist)

  // Donut chart
  const donut = [{
    type: 'pie',
    hole: 0.55,
    labels: keys.map(k => STAGE_LABEL[k] ?? k),
    values: keys.map(k => dist[k]),
    marker: { colors: keys.map(k => STAGE_COLOR[k]), line: { color: 'white', width: 2 } },
    textinfo: 'percent',
    hovertemplate: '<b>%{label}</b><br>%{value:.1f}%<extra></extra>',
    sort: false,
  }]

  // Horizontal stacked bar
  const bars = keys.map(k => ({
    type: 'bar',
    name: STAGE_LABEL[k] ?? k,
    x: [dist[k]],
    y: [''],
    orientation: 'h',
    marker: { color: STAGE_COLOR[k] },
    hovertemplate: `<b>${STAGE_LABEL[k]}</b>: %{x:.1f}%<extra></extra>`,
    text: dist[k] > 5 ? [`${dist[k]?.toFixed(0)}%`] : [''],
    textposition: 'inside',
    insidetextanchor: 'middle',
    textfont: { color: 'white', size: 11 },
  }))

  return (
    <section style={{ background: 'white', margin: 16, borderRadius: 10,
                      border: '1px solid #e0e0e0', overflow: 'hidden' }}>

      {/* title row */}
      <div style={{ padding: '14px 20px', borderBottom: '1px solid #f0f0f0',
                    display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontWeight: 700, fontSize: 16 }}>
          {data.recording_id?.toUpperCase()}
        </span>
        <span style={{
          fontSize: 12, padding: '2px 10px', borderRadius: 12,
          background: '#e3f2fd', color: '#1565c0', fontWeight: 600,
        }}>
          {data.pathology}
        </span>
        <span style={{ fontSize: 12, color: '#888', marginLeft: 'auto' }}>
          {data.n_epochs} × 30 s epochs · {data.eeg_channel}
        </span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 0, alignItems: 'flex-start' }}>
        {/* donut */}
        <div style={{ padding: '8px 0 0 8px' }}>
          <Plot
            data={donut}
            layout={{
              width: 260, height: 240,
              margin: { t: 10, b: 10, l: 10, r: 10 },
              showlegend: true,
              legend: { orientation: 'v', x: 1.02, y: 0.5, font: { size: 11 } },
              paper_bgcolor: 'transparent',
              annotations: [{
                text: `${data.sleep_efficiency_pct?.toFixed(0)}%<br><span style="font-size:10">Efficiency</span>`,
                x: 0.5, y: 0.5, showarrow: false,
                font: { size: 14, color: '#333' }, align: 'center',
              }],
            }}
            config={{ displayModeBar: false, responsive: false }}
          />
        </div>

        {/* right side: stacked bar + metric cards */}
        <div style={{ flex: 1, minWidth: 300, padding: '16px 16px 16px 0' }}>
          <div style={{ fontSize: 12, color: '#888', marginBottom: 4, paddingLeft: 4 }}>
            Stage distribution
          </div>
          <Plot
            data={bars}
            layout={{
              barmode: 'stack',
              height: 60,
              margin: { t: 4, b: 24, l: 4, r: 4 },
              showlegend: false,
              xaxis: { range: [0, 100], ticksuffix: '%', tickfont: { size: 10 } },
              yaxis: { showticklabels: false },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%' }}
          />

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
                        gap: 8, marginTop: 12 }}>
            <MetricCard label="Sleep Efficiency"
              value={`${data.sleep_efficiency_pct?.toFixed(1)}%`}
              warn={data.sleep_efficiency_pct < 80} />
            <MetricCard label="Total Sleep"
              value={`${data.tst_minutes?.toFixed(0)} min`} />
            <MetricCard label="Time in Bed"
              value={`${data.tib_minutes?.toFixed(0)} min`} />
            <MetricCard label="Sleep Onset"
              value={`${data.sol_minutes?.toFixed(0)} min`}
              warn={data.sol_minutes > 30} />
            <MetricCard label="REM Latency"
              value={data.rem_latency_minutes != null
                ? `${data.rem_latency_minutes?.toFixed(0)} min` : 'N/A'}
              warn={data.rem_latency_minutes != null && data.rem_latency_minutes < 60} />
            <MetricCard label="Transitions"
              value={data.n_transitions}
              warn={data.n_transitions > 80} />
          </div>
        </div>
      </div>
    </section>
  )
}
