import "./Dashboard.css";

// Hardcoded demo data. No fetch, no API: all literals live here.
const DASHBOARD_DATA = {
  hotelName: "Hotel Canciller — Ex Hotel Presidente",
  hotelId: "HX-001",
  lastUpdated: "2025-01-15 14:32",
  user: "Juan",
  financial: [
    {
      label: "Ingresos totales",
      value: "$4,285.23",
      unit: "USD",
      trend: "-12.3%",
      trendLabel: "vs competidores",
    },
    {
      label: "Tarifa diaria promedio",
      value: "$20.45",
      unit: "USD",
      trend: "-8.1%",
      trendLabel: "vs competidores",
    },
    {
      label: "RevPAR",
      value: "$0.25",
      unit: "USD",
      trend: "-15.0%",
      trendLabel: "vs competidores",
    },
  ],
  operational: [
    { label: "Reservas", value: "47", trend: "-5.2%", trendLabel: "vs competidores" },
    { label: "Noches de habitación", value: "66", trend: "-3.8%", trendLabel: "vs competidores" },
    {
      label: "Puntaje de tarifa",
      value: "7.9",
      max: "/10",
      trend: "-0.3",
      trendLabel: "vs competidores",
    },
  ],
  chart: {
    months: ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"],
    property: [120, 150, 180, 200, 210, 230, 250, 280, 240, 200, 180, 160],
    competitors: [200, 220, 250, 280, 300, 350, 500, 520, 400, 350, 300, 250],
  },
};

// Static tabs/controls for the chart. Purely visual, no handlers.
const CHART_TABS = ["Ingresos totales", "Tarifa diaria promedio", "RevPAR"];
const CHART_RANGES = ["Día", "Semana", "Mes"];

function HotelIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M9 9v.01M9 12v.01M9 15v.01M9 18v.01" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4M8 2v4M3 10h18" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronDown() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function TrendDown({ trend, trendLabel }) {
  return (
    <div className="metric-trend">
      <span className="trend-arrow">▼</span>
      <span className="trend-value">{trend}</span>
      <span className="trend-label">{trendLabel}</span>
    </div>
  );
}

function MetricCard({ metric }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{metric.label}</div>
      <div className="metric-value">
        {metric.value}
        {metric.max && <span className="metric-max">{metric.max}</span>}
        {metric.unit && <span className="metric-unit">{metric.unit}</span>}
      </div>
      <TrendDown trend={metric.trend} trendLabel={metric.trendLabel} />
    </div>
  );
}

// Static SVG line chart. All geometry is computed from the hardcoded series;
// there is no hover, tooltip or click behaviour.
function LineChart({ chart }) {
  const width = 920;
  const height = 280;
  const padding = { top: 20, right: 20, bottom: 32, left: 20 };
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;

  const allValues = [...chart.property, ...chart.competitors];
  const maxValue = Math.max(...allValues);
  const count = chart.months.length;

  // Map a data point to SVG coordinates.
  const xAt = (i) => padding.left + (count === 1 ? 0 : (innerW * i) / (count - 1));
  const yAt = (v) => padding.top + innerH - (innerH * v) / maxValue;

  const toPolyline = (series) => series.map((v, i) => `${xAt(i)},${yAt(v)}`).join(" ");

  const gridLines = [0, 0.25, 0.5, 0.75, 1].map((r) => padding.top + innerH * r);

  return (
    <svg
      className="line-chart"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="Comparación de ingresos: tu propiedad vs competidores"
    >
      {/* Subtle horizontal grid */}
      {gridLines.map((y, i) => (
        <line key={i} x1={padding.left} y1={y} x2={width - padding.right} y2={y} className="grid-line" />
      ))}

      {/* Competitors line (teal) */}
      <polyline points={toPolyline(chart.competitors)} className="series-competitors" />
      {chart.competitors.map((v, i) => (
        <circle key={`c-${i}`} cx={xAt(i)} cy={yAt(v)} r="3.5" className="dot-competitors" />
      ))}

      {/* Property line (purple) */}
      <polyline points={toPolyline(chart.property)} className="series-property" />
      {chart.property.map((v, i) => (
        <circle key={`p-${i}`} cx={xAt(i)} cy={yAt(v)} r="3.5" className="dot-property" />
      ))}

      {/* X axis labels */}
      {chart.months.map((m, i) => (
        <text key={m} x={xAt(i)} y={height - 8} className="axis-label" textAnchor="middle">
          {m}
        </text>
      ))}
    </svg>
  );
}

export default function Dashboard() {
  const data = DASHBOARD_DATA;

  return (
    <div className="dashboard">
      {/* 1. Top bar */}
      <header className="db-header">
        <div className="db-brand">
          <span className="db-brand-icon">
            <HotelIcon />
          </span>
          <span className="db-brand-name">Partner Smart Platform</span>
        </div>

        <nav className="db-nav">
          <span className="db-nav-link active">Hoy</span>
          <span className="db-nav-link">Oportunidades</span>
        </nav>

        <div className="db-hotel">
          <span className="db-hotel-name">{data.hotelName}</span>
          <span className="db-hotel-id">{data.hotelId}</span>
        </div>

        <div className="db-user">
          <span className="db-avatar">JU</span>
          <span className="db-user-name">{data.user}</span>
        </div>
      </header>

      {/* 2. Filters bar */}
      <div className="db-filters">
        <div className="db-filter">
          <CalendarIcon />
          <span>Año actual</span>
          <ChevronDown />
        </div>
        <div className="db-filter">
          <span>Comparar: Competidores</span>
          <ChevronDown />
        </div>
        <span className="db-download">Descargar</span>
      </div>

      {/* Main content container */}
      <div className="db-container">
        {/* 3. Financial performance */}
        <div className="db-updated">Última actualización: {data.lastUpdated}</div>
        <section className="db-cards">
          {data.financial.map((m) => (
            <MetricCard key={m.label} metric={m} />
          ))}
        </section>

        {/* 4. Line chart */}
        <section className="db-chart-card">
          <div className="db-chart-head">
            <div className="db-chart-tabs">
              {CHART_TABS.map((t, i) => (
                <span key={t} className={`chart-tab ${i === 0 ? "active" : ""}`}>
                  {t}
                </span>
              ))}
            </div>
            <div className="db-chart-ranges">
              {CHART_RANGES.map((r, i) => (
                <span key={r} className={`chart-range ${i === CHART_RANGES.length - 1 ? "active" : ""}`}>
                  {r}
                </span>
              ))}
            </div>
          </div>

          <LineChart chart={data.chart} />

          <div className="db-legend">
            <span className="legend-item">
              <span className="legend-dot dot-prop" />
              Tu propiedad
            </span>
            <span className="legend-item">
              <span className="legend-dot dot-comp" />
              Competidores
            </span>
          </div>
        </section>

        {/* 5. Operational metrics */}
        <section className="db-cards">
          {data.operational.map((m) => (
            <MetricCard key={m.label} metric={m} />
          ))}
        </section>
      </div>
    </div>
  );
}
