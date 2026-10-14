import "./Dashboard.css";
import LanguageToggle from "./LanguageToggle";

// Strings do dashboard por idioma. O painel segue 100% mockado (sem fetch),
// mas o rotulo acompanha o toggle para dar a impressao de app bilingue.
const COPY = {
  pt: {
    brand: "Partner Smart Platform",
    navToday: "Hoje",
    navOpportunities: "Oportunidades",
    yearFilter: "Ano atual",
    compareLabel: "Comparar: Concorrentes",
    download: "Baixar",
    lastUpdated: "Última atualização:",
    chartTabs: ["Receita total", "Diária média", "RevPAR"],
    chartRanges: ["Dia", "Semana", "Mês"],
    legendProperty: "Sua propriedade",
    legendCompetitors: "Concorrentes",
    chartAria: "Comparação de receita: sua propriedade vs concorrentes",
    trendVsCompetitors: "vs concorrentes",
    hotelName: "Hotel Canciller — Ex Hotel Presidente",
    financial: [
      { key: "revenue", label: "Receita total" },
      { key: "adr", label: "Diária média" },
      { key: "revpar", label: "RevPAR" },
    ],
    operational: [
      { key: "bookings", label: "Reservas" },
      { key: "nights", label: "Diárias" },
      { key: "rateScore", label: "Pontuação de tarifa" },
    ],
    months: ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"],
  },
  es: {
    brand: "Partner Smart Platform",
    navToday: "Hoy",
    navOpportunities: "Oportunidades",
    yearFilter: "Año actual",
    compareLabel: "Comparar: Competidores",
    download: "Descargar",
    lastUpdated: "Última actualización:",
    chartTabs: ["Ingresos totales", "Tarifa diaria promedio", "RevPAR"],
    chartRanges: ["Día", "Semana", "Mes"],
    legendProperty: "Tu propiedad",
    legendCompetitors: "Competidores",
    chartAria: "Comparación de ingresos: tu propiedad vs competidores",
    trendVsCompetitors: "vs competidores",
    hotelName: "Hotel Canciller — Ex Hotel Presidente",
    financial: [
      { key: "revenue", label: "Ingresos totales" },
      { key: "adr", label: "Tarifa diaria promedio" },
      { key: "revpar", label: "RevPAR" },
    ],
    operational: [
      { key: "bookings", label: "Reservas" },
      { key: "nights", label: "Noches de habitación" },
      { key: "rateScore", label: "Puntaje de tarifa" },
    ],
    months: ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"],
  },
};

// Valores numericos ficam separados do idioma: nao mudam quando o toggle troca.
const METRICS = {
  revenue: { value: "$4,285.23", unit: "USD", trend: "-12.3%" },
  adr: { value: "$20.45", unit: "USD", trend: "-8.1%" },
  revpar: { value: "$0.25", unit: "USD", trend: "-15.0%" },
  bookings: { value: "47", trend: "-5.2%" },
  nights: { value: "66", trend: "-3.8%" },
  rateScore: { value: "7.9", max: "/10", trend: "-0.3" },
};

const DASHBOARD_DATA = {
  hotelId: "HX-001",
  lastUpdated: "2025-01-15 14:32",
  user: "Juan",
  chart: {
    property: [120, 150, 180, 200, 210, 230, 250, 280, 240, 200, 180, 160],
    competitors: [200, 220, 250, 280, 300, 350, 500, 520, 400, 350, 300, 250],
  },
};

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

function MetricCard({ label, metric, trendLabel }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {metric.value}
        {metric.max && <span className="metric-max">{metric.max}</span>}
        {metric.unit && <span className="metric-unit">{metric.unit}</span>}
      </div>
      <TrendDown trend={metric.trend} trendLabel={trendLabel} />
    </div>
  );
}

// Static SVG line chart. All geometry is computed from the hardcoded series;
// there is no hover, tooltip or click behaviour.
function LineChart({ chart, months, ariaLabel }) {
  const width = 920;
  const height = 280;
  const padding = { top: 20, right: 20, bottom: 32, left: 20 };
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;

  const allValues = [...chart.property, ...chart.competitors];
  const maxValue = Math.max(...allValues);
  const count = months.length;

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
      aria-label={ariaLabel}
    >
      {gridLines.map((y, i) => (
        <line key={i} x1={padding.left} y1={y} x2={width - padding.right} y2={y} className="grid-line" />
      ))}

      <polyline points={toPolyline(chart.competitors)} className="series-competitors" />
      {chart.competitors.map((v, i) => (
        <circle key={`c-${i}`} cx={xAt(i)} cy={yAt(v)} r="3.5" className="dot-competitors" />
      ))}

      <polyline points={toPolyline(chart.property)} className="series-property" />
      {chart.property.map((v, i) => (
        <circle key={`p-${i}`} cx={xAt(i)} cy={yAt(v)} r="3.5" className="dot-property" />
      ))}

      {months.map((m, i) => (
        <text key={m} x={xAt(i)} y={height - 8} className="axis-label" textAnchor="middle">
          {m}
        </text>
      ))}
    </svg>
  );
}

export default function Dashboard({ language = "es", onLanguageChange }) {
  const t = COPY[language] || COPY.es;
  const data = DASHBOARD_DATA;

  return (
    <div className="dashboard">
      <header className="db-header">
        <div className="db-brand">
          <span className="db-brand-icon">
            <HotelIcon />
          </span>
          <span className="db-brand-name">{t.brand}</span>
        </div>

        <nav className="db-nav">
          <span className="db-nav-link active">{t.navToday}</span>
          <span className="db-nav-link">{t.navOpportunities}</span>
        </nav>

        <div className="db-hotel">
          <span className="db-hotel-name">{t.hotelName}</span>
          <span className="db-hotel-id">{data.hotelId}</span>
        </div>

        <div className="db-user">
          {onLanguageChange && (
            <LanguageToggle
              value={language}
              onChange={onLanguageChange}
              placement="landing"
            />
          )}
          <span className="db-avatar">JU</span>
          <span className="db-user-name">{data.user}</span>
        </div>
      </header>

      <div className="db-filters">
        <div className="db-filter">
          <CalendarIcon />
          <span>{t.yearFilter}</span>
          <ChevronDown />
        </div>
        <div className="db-filter">
          <span>{t.compareLabel}</span>
          <ChevronDown />
        </div>
        <span className="db-download">{t.download}</span>
      </div>

      <div className="db-container">
        <div className="db-updated">
          {t.lastUpdated} {data.lastUpdated}
        </div>
        <section className="db-cards">
          {t.financial.map((f) => (
            <MetricCard
              key={f.key}
              label={f.label}
              metric={METRICS[f.key]}
              trendLabel={t.trendVsCompetitors}
            />
          ))}
        </section>

        <section className="db-chart-card">
          <div className="db-chart-head">
            <div className="db-chart-tabs">
              {t.chartTabs.map((tab, i) => (
                <span key={tab} className={`chart-tab ${i === 0 ? "active" : ""}`}>
                  {tab}
                </span>
              ))}
            </div>
            <div className="db-chart-ranges">
              {t.chartRanges.map((r, i) => (
                <span
                  key={r}
                  className={`chart-range ${i === t.chartRanges.length - 1 ? "active" : ""}`}
                >
                  {r}
                </span>
              ))}
            </div>
          </div>

          <LineChart chart={data.chart} months={t.months} ariaLabel={t.chartAria} />

          <div className="db-legend">
            <span className="legend-item">
              <span className="legend-dot dot-prop" />
              {t.legendProperty}
            </span>
            <span className="legend-item">
              <span className="legend-dot dot-comp" />
              {t.legendCompetitors}
            </span>
          </div>
        </section>

        <section className="db-cards">
          {t.operational.map((o) => (
            <MetricCard
              key={o.key}
              label={o.label}
              metric={METRICS[o.key]}
              trendLabel={t.trendVsCompetitors}
            />
          ))}
        </section>
      </div>
    </div>
  );
}
