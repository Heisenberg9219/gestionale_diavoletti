import { useEffect, useMemo, useState } from "react";
import { BarChart3, Download, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { downloadFile, request } from "../api";
import "../products.css";

const list = (data) => data?.results || data || [];
const metrics = { REVENUE: "Incassi", SALES: "Numero vendite", UNITS: "Articoli venduti", DISCOUNTS: "Sconti", GROSS_MARGIN: "Margine stimato", RETURNS: "Resi", INVENTORY_VALUE: "Valore magazzino", INVENTORY_VARIANCE: "Differenze inventariali" };
const periods = { TODAY: "Oggi", THIS_WEEK: "Questa settimana", THIS_MONTH: "Questo mese", LAST_30_DAYS: "Ultimi 30 giorni", THIS_YEAR: "Anno corrente" };
const groups = { NONE: "Nessun raggruppamento", DAY: "Giorno", WEEK: "Settimana", MONTH: "Mese", CHANNEL: "Canale", BRAND: "Marca", CATEGORY: "Categoria", PROMOTION: "Promozione" };
const emptyForm = { title: "", metric: "REVENUE", period: "THIS_MONTH", group_by: "DAY", visualization: "BAR", compare_previous_period: true };
const moneyMetrics = new Set(["REVENUE", "DISCOUNTS", "GROSS_MARGIN", "RETURNS", "INVENTORY_VALUE", "INVENTORY_VARIANCE"]);
const euro = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });

export default function ReportsPage() {
  const [dashboards, setDashboards] = useState([]);
  const [widgets, setWidgets] = useState([]);
  const [results, setResults] = useState({});
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);
  const [saving, setSaving] = useState(false);

  const notice = (text, ok = true) => { setSuccess(ok); setMessage(text); };
  const format = (widget, value) => moneyMetrics.has(widget.metric) ? euro.format(Number(value || 0)) : new Intl.NumberFormat("it-IT").format(Number(value || 0));
  const fetchResults = async (items) => {
    const values = await Promise.all(items.map(async (widget) => {
      try { return [widget.id, await request(`/reporting/widgets/${widget.id}/calculate/`)]; } catch { return [widget.id, null]; }
    }));
    setResults(Object.fromEntries(values));
  };
  const load = async () => {
    try {
      const dashboardData = list(await request("/reporting/dashboards/?is_active=true"));
      setDashboards(dashboardData);
      const widgetData = list(await request("/reporting/widgets/"));
      setWidgets(widgetData);
      await fetchResults(widgetData);
    } catch (error) { notice(error.message || "Impossibile caricare i report.", false); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!message) return undefined; const timer = setTimeout(() => setMessage(""), 4000); return () => clearTimeout(timer); }, [message]);

  const totalRevenue = useMemo(() => widgets.filter((widget) => widget.metric === "REVENUE").reduce((total, widget) => total + Number(results[widget.id]?.value || 0), 0), [widgets, results]);
  const openCreate = () => { setForm(emptyForm); setFormOpen(true); setMessage(""); };
  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }));
  async function resolveDashboard() {
    if (dashboards.length) return dashboards[0];
    const created = await request("/reporting/dashboards/", { method: "POST", body: JSON.stringify({ code: `REPORT-${Date.now()}`, name: "Report negozio", description: "Dashboard principale dei report", is_active: true }) });
    setDashboards([created]);
    return created;
  }
  async function createWidget(event) {
    event.preventDefault(); setSaving(true);
    try {
      const dashboard = await resolveDashboard();
      await request("/reporting/widgets/", { method: "POST", body: JSON.stringify({ ...form, dashboard: dashboard.id, title: form.title.trim(), position: widgets.length, width: 1, height: 1, filters: {}, auto_refresh_daily: true }) });
      setFormOpen(false); notice("Report creato correttamente."); await load();
    } catch (error) { notice(error.message, false); } finally { setSaving(false); }
  }
  async function refresh(widget) {
    try { await request(`/reporting/widgets/${widget.id}/refresh/`, { method: "POST", body: JSON.stringify({}) }); await fetchResults(widgets); notice("Report aggiornato correttamente."); }
    catch (error) { notice(error.message, false); }
  }
  async function remove(widget) {
    if (!window.confirm(`Eliminare il report “${widget.title}”?`)) return;
    try { await request(`/reporting/widgets/${widget.id}/`, { method: "DELETE" }); notice("Report eliminato correttamente."); await load(); }
    catch (error) { notice(error.message, false); }
  }
  async function exportCsv(widget) {
    try { await downloadFile(`/reporting/widgets/${widget.id}/export-csv/`, `${widget.title.toLowerCase().replace(/\s+/g, "-")}.csv`, { method: "POST" }); }
    catch (error) { notice(error.message, false); }
  }

  return <section className="products-page reports-page">
    <style>{`.report-form{display:grid;grid-template-columns:1.25fr repeat(4,minmax(120px,1fr));gap:14px;align-items:end;padding:20px;border-radius:14px;background:#fff;box-shadow:0 7px 22px #25171a09}.report-form label{display:grid;gap:6px;font-size:11px;font-weight:900}.report-form input,.report-form select{box-sizing:border-box;width:100%;height:42px;border:1px solid #ded9db;border-radius:8px;padding:0 10px;background:#fff;font:inherit}.report-copy{grid-row:span 2}.report-form .report-toggle{display:flex;align-items:center;gap:9px;min-height:42px;padding:0 12px;border:1px solid #ded9db;border-radius:8px;background:#fff;font-size:12px;cursor:pointer}.report-form .report-toggle input{width:18px;height:18px;margin:0;padding:0;accent-color:#ed001b}.report-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:18px}.report-summary article{display:grid;gap:5px;padding:17px;border:1px solid #e8e2e4;border-radius:8px;background:#fff;box-shadow:0 7px 22px #25171a09}.report-summary span{color:#777176;font-size:12px}.report-summary strong{font-size:24px}.report-summary article:last-child strong{color:#b70018}.report-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.report-card{display:grid;gap:16px;padding:19px;border:1px solid #e8e2e4;border-radius:8px;background:#fff;box-shadow:0 7px 22px #25171a09}.report-card-header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.report-card-header p{margin:0 0 4px;color:#777176;font-size:11px;font-weight:800}.report-card-header h3{margin:0;font-size:16px}.report-card-actions{display:flex;gap:6px}.report-card-actions button{display:grid;width:32px;height:32px;place-items:center;border:1px solid #e2dddf;border-radius:7px;background:#fff;color:#4d464c;cursor:pointer}.report-card-actions button:last-child{color:#b70018}.report-card-actions button:hover{border-color:#ed001b;color:#b70018}.report-value{display:flex;align-items:baseline;gap:8px}.report-value strong{font-size:29px}.report-value span{color:#777176;font-size:12px}.report-comparison{color:#167444;font-size:12px;font-weight:800}.report-comparison.down{color:#b70018}.report-series{display:grid;gap:8px;border-top:1px solid #f0ebed;padding-top:14px}.report-series-row{display:grid;grid-template-columns:minmax(70px,.55fr) minmax(60px,1fr) auto;gap:9px;align-items:center}.report-series-row span{overflow:hidden;color:#777176;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.report-series-bar{height:8px;overflow:hidden;border-radius:99px;background:#f1eef0}.report-series-bar i{display:block;height:100%;border-radius:inherit;background:#ed001b}.report-series-row b{font-size:11px}.report-card-footer{color:#777176;font-size:11px}.report-empty{grid-column:1/-1}.report-top-actions{display:flex;gap:9px}.report-top-actions button{display:flex;align-items:center;gap:7px}.report-heading-note{margin:0 0 15px;color:#777176;font-size:12px}@media(max-width:1000px){.report-form{grid-template-columns:1fr 1fr}.report-copy{grid-column:1/-1;grid-row:auto}.report-grid{grid-template-columns:1fr}}@media(max-width:620px){.report-form{grid-template-columns:1fr}.report-form .inline-form-actions button{flex:1}.report-summary{grid-template-columns:1fr}.report-card{padding:16px}.report-value strong{font-size:25px}}`}</style>
    <div className="page-title-row"><div><p className="eyebrow">Controllo</p><h2>Report</h2><span>Analizza vendite, margini, articoli e andamento del negozio.</span></div><div className="report-top-actions"><button className="secondary-action" onClick={() => fetchResults(widgets)}><RefreshCw size={17} /> Aggiorna</button><button className="primary-action" onClick={openCreate}><Plus size={17} /> Nuovo report</button></div></div>
    {formOpen && <form className="report-form" onSubmit={createWidget}><div className="inventory-form-copy report-copy"><p className="eyebrow">Nuovo report</p><h3>Configura un indicatore</h3><span>Scegli il dato, il periodo e il modo in cui vuoi analizzarlo.</span></div><label>Titolo<input required value={form.title} onChange={(event) => update("title", event.target.value)} placeholder="Es. Incassi mensili" /></label><label>Metrica<select value={form.metric} onChange={(event) => update("metric", event.target.value)}>{Object.entries(metrics).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Periodo<select value={form.period} onChange={(event) => update("period", event.target.value)}>{Object.entries(periods).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Raggruppa per<select value={form.group_by} onChange={(event) => update("group_by", event.target.value)}>{Object.entries(groups).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Visualizzazione<select value={form.visualization} onChange={(event) => update("visualization", event.target.value)}><option value="KPI">Valore</option><option value="BAR">Istogramma</option><option value="LINE">Linea</option><option value="TABLE">Tabella</option></select></label><label className="report-toggle"><input type="checkbox" checked={form.compare_previous_period} onChange={(event) => update("compare_previous_period", event.target.checked)} /><span>Confronta periodo precedente</span></label><div className="inline-form-actions"><button className="secondary-action" type="button" onClick={() => setFormOpen(false)}><X size={17} /> Annulla</button><button className="primary-action" disabled={saving}>{saving ? "Creazione..." : "Crea report"}</button></div></form>}
    {message && <p className={success ? "operation-success" : "catalog-error"}>{message}</p>}
    <section className="report-summary"><article><span>Report attivi</span><strong>{widgets.length}</strong></article><article><span>Dashboard</span><strong>{dashboards.length || 0}</strong></article><article><span>Incassi nei report</span><strong>{euro.format(totalRevenue)}</strong></article></section>
    <p className="report-heading-note">Ogni report può essere aggiornato, scaricato in CSV o eliminato singolarmente.</p>
    <section className="report-grid">{!widgets.length ? <div className="empty-product-state report-empty"><BarChart3 size={28} /><strong>Nessun report configurato</strong><span>Crea il primo indicatore per iniziare a leggere i dati del negozio.</span></div> : widgets.map((widget) => { const result = results[widget.id]; const series = result?.series || []; const max = Math.max(...series.map((item) => Number(item.value || 0)), 1); const change = result?.previous_value === undefined ? null : Number(result.value || 0) - Number(result.previous_value || 0); return <article className="report-card" key={widget.id}><div className="report-card-header"><div><p>{metrics[widget.metric]} · {periods[widget.period]}</p><h3>{widget.title}</h3></div><div className="report-card-actions"><button type="button" title="Aggiorna report" onClick={() => refresh(widget)}><RefreshCw size={15} /></button><button type="button" title="Scarica CSV" onClick={() => exportCsv(widget)}><Download size={15} /></button><button type="button" title="Elimina report" onClick={() => remove(widget)}><Trash2 size={15} /></button></div></div><div className="report-value"><strong>{result ? format(widget, result.value) : "-"}</strong><span>{result ? `${result.date_from} - ${result.date_to}` : "Caricamento"}</span></div>{change !== null && <span className={`report-comparison ${change < 0 ? "down" : ""}`}>{change >= 0 ? "+" : ""}{format(widget, change)} rispetto al periodo precedente</span>}{series.length > 0 && <div className="report-series">{series.slice(0, 5).map((item) => <div className="report-series-row" key={item.label}><span>{item.label}</span><div className="report-series-bar"><i style={{ width: `${Math.max(4, Number(item.value || 0) / max * 100)}%` }} /></div><b>{format(widget, item.value)}</b></div>)}</div>}<span className="report-card-footer">{groups[widget.group_by] || "Nessun raggruppamento"}</span></article>; })}</section>
  </section>;
}
