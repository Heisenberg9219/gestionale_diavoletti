export default function MetricCard({ label, value, change, tone = "neutral", icon: Icon }) {
  return (
    <article className={`metric-card ${tone}`}>
      <div className="metric-icon"><Icon size={20} /></div>
      <p>{label}</p>
      <strong>{value}</strong>
      <span>{change}</span>
    </article>
  );
}
