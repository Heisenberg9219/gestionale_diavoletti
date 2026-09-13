import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleAlert, Link2, Plus, Store, Trash2, X } from "lucide-react";
import { request } from "../api";
import "../products.css";

const list = (data) => data?.results || data || [];
const emptyForm = { code: "", name: "", shop_domain: "", api_version: "2026-07", credentials_env_prefix: "SHOPIFY", default_sale_location: "", is_active: true };

export default function IntegrationsPage() {
  const [connections, setConnections] = useState([]);
  const [locations, setLocations] = useState([]);
  const [events, setEvents] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);

  const notice = (text, ok = true) => { setSuccess(ok); setMessage(text); };
  const load = async () => {
    try {
      const [connectionData, locationData, eventData] = await Promise.all([
        request("/integrations/connections/"),
        request("/core/locations/"),
        request("/integrations/sync-events/?ordering=-created_at"),
      ]);
      setConnections(list(connectionData));
      setLocations(list(locationData));
      setEvents(list(eventData).slice(0, 8));
    } catch (error) {
      notice(error.message || "Impossibile caricare le integrazioni.", false);
    }
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { if (!message) return undefined; const timer = setTimeout(() => setMessage(""), 4000); return () => clearTimeout(timer); }, [message]);

  const connectionName = useMemo(() => Object.fromEntries(connections.map((item) => [item.id, item.name])), [connections]);
  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }));
  const openCreate = () => { setEditingId(null); setForm({ ...emptyForm, default_sale_location: locations[0]?.id || "" }); setFormOpen(true); setMessage(""); };
  const openEdit = (connection) => { setEditingId(connection.id); setForm({ code: connection.code, name: connection.name, shop_domain: connection.shop_domain || "", api_version: connection.api_version || "2026-07", credentials_env_prefix: connection.credentials_env_prefix || "SHOPIFY", default_sale_location: connection.default_sale_location || "", is_active: connection.is_active }); setFormOpen(true); setMessage(""); };

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    try {
      const payload = { ...form, code: form.code.trim().toUpperCase().replace(/[^A-Z0-9_]/g, "_"), name: form.name.trim(), shop_domain: form.shop_domain.trim(), credentials_env_prefix: form.credentials_env_prefix.trim().toUpperCase().replace(/[^A-Z0-9_]/g, "_"), default_sale_location: form.default_sale_location || null, provider: "SHOPIFY" };
      await request(editingId ? `/integrations/connections/${editingId}/` : "/integrations/connections/", { method: editingId ? "PATCH" : "POST", body: JSON.stringify(payload) });
      setFormOpen(false);
      notice(editingId ? "Integrazione aggiornata correttamente." : "Integrazione Shopify aggiunta correttamente.");
      await load();
    } catch (error) { notice(error.message, false); } finally { setSaving(false); }
  }

  async function toggleConnection(connection) {
    try { await request(`/integrations/connections/${connection.id}/`, { method: "PATCH", body: JSON.stringify({ is_active: !connection.is_active }) }); notice(connection.is_active ? "Integrazione disattivata." : "Integrazione attivata."); await load(); }
    catch (error) { notice(error.message, false); }
  }

  async function removeConnection(connection) {
    if (!window.confirm(`Eliminare l'integrazione “${connection.name}”?`)) return;
    try { await request(`/integrations/connections/${connection.id}/`, { method: "DELETE" }); notice("Integrazione eliminata correttamente."); await load(); }
    catch (error) { notice(error.message, false); }
  }

  const dateTime = (value) => value ? new Intl.DateTimeFormat("it-IT", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Mai";

  return <section className="products-page integrations-page">
    <style>{`.integrations-form{display:grid;grid-template-columns:1.25fr repeat(4,minmax(120px,1fr));gap:14px;align-items:end;padding:20px;border-radius:14px;background:#fff;box-shadow:0 7px 22px #25171a09}.integrations-form label{display:grid;gap:6px;font-size:11px;font-weight:900}.integrations-form input,.integrations-form select{box-sizing:border-box;width:100%;height:42px;border:1px solid #ded9db;border-radius:8px;padding:0 10px;background:#fff;font:inherit}.integration-copy{grid-column:1;grid-row:1/span 3}.integrations-form .integration-name{grid-column:2}.integrations-form .integration-code{grid-column:3}.integrations-form .integration-api{grid-column:4}.integrations-form .integration-prefix{grid-column:5}.integrations-form .integration-domain{grid-column:2/5;grid-row:2}.integrations-form .integration-location{grid-column:5;grid-row:2}.integrations-form .notification-control{grid-column:2/4;grid-row:3;display:flex;align-items:center;gap:9px;min-height:42px;padding:0 12px;border:1px solid #ded9db;border-radius:8px;background:#fff;font-size:12px;cursor:pointer}.integrations-form .notification-control input{width:18px;height:18px;margin:0;padding:0;accent-color:#ed001b}.integrations-form .integration-actions{grid-column:4/-1;grid-row:3;justify-self:end}.integration-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.integration-card{display:grid;gap:15px;padding:19px;border:1px solid #e8e2e4;border-radius:8px;background:#fff;box-shadow:0 7px 22px #25171a09}.integration-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.integration-provider{display:flex;align-items:center;gap:10px}.integration-provider svg{padding:9px;border-radius:8px;background:#fff0f2;color:#d8001d}.integration-provider strong{display:block;font-size:15px}.integration-provider span,.integration-meta span{color:#777176;font-size:12px}.integration-status{padding:5px 8px;border-radius:7px;background:#edf9f1;color:#167444;font-size:10px;font-style:normal;font-weight:900}.integration-status.off{background:#f1eff0;color:#625b60}.integration-meta{display:grid;grid-template-columns:1fr 1fr;gap:9px;border-top:1px solid #f0ebed;padding-top:13px}.integration-meta b{display:block;margin-top:3px;color:#29242a;font-size:12px}.integration-card-footer{display:flex;align-items:center;justify-content:space-between;gap:10px}.integration-card-footer button{height:34px;border:1px solid #e2dddf;border-radius:7px;padding:0 10px;background:#fff;color:#403a3f;font:inherit;font-size:11px;font-weight:800;cursor:pointer}.integration-card-footer button:last-child{display:grid;width:34px;padding:0;place-items:center;color:#b70018}.integration-card-footer button:hover{border-color:#ed001b}.integration-events{margin-top:20px}.integration-events h3{margin:0 0 10px;font-size:16px}.integration-event-row{display:grid;grid-template-columns:130px minmax(0,1fr) 130px 120px;gap:15px;align-items:center;border-top:1px solid #eeeaea;padding:14px 18px}.integration-event-row:first-of-type{border-top:0}.integration-event-row strong{font-size:12px}.integration-event-row span{overflow:hidden;color:#777176;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.integration-event-status{justify-self:start;padding:5px 8px;border-radius:7px;background:#fff3d9;color:#a56800;font-size:10px;font-style:normal;font-weight:900}.integration-event-status.succeeded{background:#edf9f1;color:#167444}.integration-event-status.failed{background:#fff0f2;color:#b00019}@media(max-width:1050px){.integrations-form{grid-template-columns:1fr 1fr}.integration-copy{grid-column:1/-1;grid-row:auto}.integrations-form .integration-name,.integrations-form .integration-code,.integrations-form .integration-domain,.integrations-form .integration-api,.integrations-form .integration-prefix,.integrations-form .integration-location,.integrations-form .notification-control,.integrations-form .integration-actions{grid-column:auto;grid-row:auto;justify-self:stretch}.integration-grid{grid-template-columns:1fr}.integration-event-row{grid-template-columns:105px 1fr auto}.integration-event-row span:last-child{display:none}}@media(max-width:600px){.integrations-form{grid-template-columns:1fr}.integrations-form .inline-form-actions button{flex:1}.integration-event-row{grid-template-columns:1fr auto}.integration-event-row span{display:none}.integration-event-status{grid-column:2;grid-row:1}}`}</style>
    <div className="page-title-row"><div><p className="eyebrow">Controllo</p><h2>Integrazioni</h2><span>Collega il gestionale ai servizi esterni e tieni sotto controllo le sincronizzazioni.</span></div><button className="primary-action" onClick={openCreate}><Plus size={17} /> Nuova integrazione</button></div>
    {formOpen && <form className="integrations-form" onSubmit={save}><div className="inventory-form-copy integration-copy"><p className="eyebrow">{editingId ? "Modifica collegamento" : "Nuovo collegamento"}</p><h3>Collega Shopify</h3><span>Il token non viene salvato qui: resta protetto nelle variabili d’ambiente del server.</span></div><label className="integration-name">Nome integrazione<input required value={form.name} onChange={(event) => update("name", event.target.value)} placeholder="Es. Shop online" /></label><label className="integration-code">Codice<input required value={form.code} onChange={(event) => update("code", event.target.value)} placeholder="SHOP_ONLINE" /></label><label className="integration-domain">Dominio Shopify<input required value={form.shop_domain} onChange={(event) => update("shop_domain", event.target.value)} placeholder="negozio.myshopify.com" /></label><label className="integration-api">Versione API<input required value={form.api_version} onChange={(event) => update("api_version", event.target.value)} /></label><label className="integration-prefix">Prefisso credenziali<input required value={form.credentials_env_prefix} onChange={(event) => update("credentials_env_prefix", event.target.value)} placeholder="SHOPIFY" /></label><label className="integration-location">Sede vendite online<select value={form.default_sale_location} onChange={(event) => update("default_sale_location", event.target.value)}><option value="">Non impostata</option>{locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label><label className="notification-control"><input type="checkbox" checked={form.is_active} onChange={(event) => update("is_active", event.target.checked)} /><span>Integrazione attiva</span></label><div className="inline-form-actions integration-actions"><button type="button" className="secondary-action" onClick={() => setFormOpen(false)}><X size={17} /> Annulla</button><button className="primary-action" disabled={saving}>{saving ? "Salvataggio..." : editingId ? "Salva modifiche" : "Crea integrazione"}</button></div></form>}
    {message && <p className={success ? "operation-success" : "catalog-error"}>{message}</p>}
    <section className="integration-grid">{!connections.length ? <div className="empty-product-state"><Link2 size={28} /><strong>Nessuna integrazione configurata</strong><span>Aggiungi il primo collegamento Shopify per sincronizzare l’e-commerce.</span></div> : connections.map((connection) => <article className="integration-card" key={connection.id}><div className="integration-card-head"><div className="integration-provider"><Store size={21} /><div><strong>{connection.name}</strong><span>{connection.shop_domain || "Dominio non impostato"}</span></div></div><em className={`integration-status ${connection.is_active ? "" : "off"}`}>{connection.is_active ? "Attiva" : "Disattivata"}</em></div><div className="integration-meta"><div><span>Ultima sincronizzazione</span><b>{dateTime(connection.last_success_at)}</b></div><div><span>Sede online</span><b>{locations.find((item) => item.id === connection.default_sale_location)?.name || "Non impostata"}</b></div></div>{connection.last_error && <span className="catalog-error"><CircleAlert size={15} /> {connection.last_error}</span>}<div className="integration-card-footer"><div><button type="button" onClick={() => toggleConnection(connection)}>{connection.is_active ? "Disattiva" : "Attiva"}</button><button type="button" onClick={() => openEdit(connection)}>Configura</button></div><button type="button" title="Elimina integrazione" aria-label={`Elimina ${connection.name}`} onClick={() => removeConnection(connection)}><Trash2 size={16} /></button></div></article>)}</section>
    <section className="products-list integration-events"><h3>Ultime sincronizzazioni</h3>{!events.length ? <div className="empty-product-state"><CheckCircle2 size={26} /><strong>Nessun evento di sincronizzazione</strong><span>Gli aggiornamenti di magazzino e prodotti compariranno qui.</span></div> : events.map((event) => <div className="integration-event-row" key={event.id}><strong>{connectionName[event.connection] || "Integrazione"}</strong><span>{event.event_type === "INVENTORY" ? "Aggiornamento giacenza" : event.event_type === "PRODUCT" ? "Aggiornamento prodotto" : "Aggiornamento ordine"}</span><em className={`integration-event-status ${event.status.toLowerCase()}`}>{event.status === "SUCCEEDED" ? "Completato" : event.status === "FAILED" ? "Fallito" : event.status === "RETRY" ? "Da riprovare" : "In attesa"}</em><span>{dateTime(event.created_at)}</span></div>)}</section>
  </section>;
}
