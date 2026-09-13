import { useEffect, useMemo, useState } from "react";
import { BadgePercent, CalendarDays, CircleStop, Plus, Search } from "lucide-react";
import { request } from "../api";
import "../products.css";

const list = (data) => data?.results || data || [];
const newCode = (prefix) => `${prefix}-${Date.now()}`;
const now = () => new Date().toISOString().slice(0, 16);
const blankPromotion = () => ({ name: "", campaign_type: "PROMOTION", discount_type: "PERCENTAGE", value: "", brand: "", valid_from: now(), valid_until: "", notes: "" });
const typeLabel = { PROMOTION: "Promozione", SALE: "Saldi" };
const activationLabel = { ENABLED: "Attiva", ENDED: "Terminata", CANCELLED: "Annullata" };

export default function PromotionsPage() {
  const [campaigns, setCampaigns] = useState([]); const [activations, setActivations] = useState([]); const [offers, setOffers] = useState([]); const [rules, setRules] = useState([]); const [brands, setBrands] = useState([]); const [brandScopes, setBrandScopes] = useState([]);
  const [query, setQuery] = useState(""); const [filter, setFilter] = useState("ENABLED"); const [formOpen, setFormOpen] = useState(false); const [form, setForm] = useState(blankPromotion());
  const [saving, setSaving] = useState(false); const [message, setMessage] = useState(""); const [success, setSuccess] = useState(false);

  const notice = (text, ok = true) => { setSuccess(ok); setMessage(text); };
  const load = async () => { try { const [campaignData, activationData, offerData, ruleData, brandData, scopeData] = await Promise.all([request("/promotions/campaigns/"), request("/promotions/activations/"), request("/promotions/offers/"), request("/promotions/rules/"), request("/catalog/brands/?active=true"), request("/promotions/offer-brands/")]); setCampaigns(list(campaignData)); setActivations(list(activationData)); setOffers(list(offerData)); setRules(list(ruleData)); setBrands(list(brandData)); setBrandScopes(list(scopeData)); } catch (error) { notice(error.message, false); } };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!message) return undefined; const timer = setTimeout(() => setMessage(""), 4000); return () => clearTimeout(timer); }, [message]);

  const data = useMemo(() => campaigns.map((campaign) => {
    const activation = activations.find((item) => item.campaign === campaign.id && item.status === "ENABLED") || activations.find((item) => item.campaign === campaign.id);
    const offer = offers.find((item) => item.campaign === campaign.id);
    const rule = rules.find((item) => item.id === offer?.rule);
    const scope = brandScopes.find((item) => item.offer === offer?.id && item.mode === "INCLUDE");
    const brand = brands.find((item) => item.id === scope?.brand);
    return { campaign, activation, rule, brand };
  }).filter(({ campaign, activation }) => {
    const text = `${campaign.name} ${campaign.code}`.toLowerCase();
    return (!query.trim() || text.includes(query.trim().toLowerCase())) && (filter === "ALL" || activation?.status === filter);
  }), [campaigns, activations, offers, rules, query, filter]);

  async function createPromotion(event) {
    event.preventDefault();
    if (!form.valid_until) return notice("Imposta una data di fine per la promozione.", false);
    if (new Date(form.valid_until) <= new Date(form.valid_from)) return notice("La data di fine deve essere successiva all'inizio.", false);
    setSaving(true); setMessage("");
    try {
      const fixed = form.discount_type === "FIXED_DISCOUNT";
      const rule = await request("/promotions/rules/", { method: "POST", body: JSON.stringify({ code: newCode("PROMO-R"), name: form.name, description: form.notes, rule_type: form.discount_type, required_quantity: 1, discounted_quantity: 1, discount_percentage: fixed ? null : form.value, fixed_discount_amount: fixed ? form.value : null, fixed_discount_scope: "PER_ITEM", repeatable: false, grouping_mode: "ANY_ELIGIBLE", target_selection: "ALL", is_active: true }) });
      const campaign = await request("/promotions/campaigns/", { method: "POST", body: JSON.stringify({ code: newCode("PROMO"), name: form.name, campaign_type: form.campaign_type, is_active: true, notes: form.notes }) });
      const offer = await request("/promotions/offers/", { method: "POST", body: JSON.stringify({ campaign: campaign.id, rule: rule.id, code: newCode("OFFERTA"), name: form.name, is_active: true, sort_order: 0 }) });
      if (form.brand) await request("/promotions/offer-brands/", { method: "POST", body: JSON.stringify({ offer: offer.id, brand: form.brand, mode: "INCLUDE" }) });
      await request(`/promotions/campaigns/${campaign.id}/activate/`, { method: "POST", body: JSON.stringify({ valid_from: new Date(form.valid_from).toISOString(), valid_until: new Date(form.valid_until).toISOString() }) });
      setFormOpen(false); setForm(blankPromotion()); notice("Promozione creata e attivata per tutti i clienti."); await load();
    } catch (error) { notice(error.message, false); } finally { setSaving(false); }
  }

  async function endPromotion(item) {
    try { await request(`/promotions/activations/${item.id}/end/`, { method: "POST", body: JSON.stringify({}) }); notice("Promozione terminata correttamente."); await load(); } catch (error) { notice(error.message, false); }
  }

  const formatDate = (value) => value ? new Intl.DateTimeFormat("it-IT", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Non indicata";
  const discount = (rule) => !rule ? "Regola non disponibile" : rule.rule_type === "FIXED_DISCOUNT" ? `-${Number(rule.fixed_discount_amount || 0).toLocaleString("it-IT", { style: "currency", currency: "EUR" })}` : `-${rule.discount_percentage}%`;

  return <section className="products-page promotions-page">
    <style>{`.promotion-form{display:grid;grid-template-columns:1.25fr repeat(3,minmax(150px,1fr));gap:14px;align-items:end;padding:20px;border-radius:14px;background:#fff;box-shadow:0 7px 22px #25171a09}.promotion-form label{display:grid;gap:6px;font-size:11px;font-weight:900}.promotion-form input,.promotion-form select{box-sizing:border-box;width:100%;height:42px;border:1px solid #ded9db;border-radius:8px;padding:0 10px;background:#fff;font:inherit}.promotion-copy{grid-row:span 2}.promotion-form .promotion-notes{grid-column:2/4}.promotion-heading,.promotion-row{display:grid;grid-template-columns:minmax(180px,1.35fr) 120px 120px 130px minmax(190px,.9fr) 112px 110px;align-items:center;gap:18px;padding:15px 22px}.promotion-heading{color:#8b858a;font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase}.promotion-row{border-top:1px solid #eeeaea}.promotion-row>div{display:grid;gap:4px}.promotion-row strong{font-size:13px}.promotion-row span{color:#817b80;font-size:12px}.promotion-row b{color:#b70018;font-size:14px}.promotion-status{justify-self:start;padding:5px 8px;border-radius:7px;background:#edf9f1;color:#167444;font-size:10px;font-style:normal;font-weight:900}.promotion-status.ended{background:#f1eff0;color:#6f676c}.promotion-status.cancelled{background:#fff0f2;color:#b00019}.promotion-end{display:flex;align-items:center;justify-content:center;gap:6px;height:33px;border:0;border-radius:7px;padding:0 10px;background:#ed001b;color:#fff;font-size:11px;font-weight:900;cursor:pointer}@media(max-width:960px){.promotion-form{grid-template-columns:1fr 1fr}.promotion-copy{grid-column:1/-1;grid-row:auto}.promotion-form .promotion-notes{grid-column:auto}.promotion-heading{display:none}.promotion-row{grid-template-columns:1fr auto;padding:16px}.promotion-row>span,.promotion-row>b{display:none}.promotion-status{grid-column:2;grid-row:1}.promotion-end{grid-column:1;grid-row:2;justify-self:start}}@media(max-width:560px){.promotion-form{grid-template-columns:1fr}.promotion-form .inline-form-actions button{flex:1}.voucher-filters{align-items:stretch;flex-direction:column}.status-tabs{overflow-x:auto;padding-bottom:2px;white-space:nowrap}}`}</style>
    <div className="page-title-row"><div><p className="eyebrow">Marketing</p><h2>Promozioni</h2><span>Campagne e sconti automatici validi per tutti i clienti.</span></div><button className="primary-action" onClick={() => { setForm(blankPromotion()); setFormOpen(true); }}><Plus size={17} /> Nuova promozione</button></div>
    {formOpen && <form className="promotion-form" onSubmit={createPromotion}><div className="inventory-form-copy promotion-copy"><p className="eyebrow">Nuova campagna</p><h3>Crea una promozione</h3><span>Lo sconto verrà proposto automaticamente in vendita durante il periodo scelto.</span></div><label>Nome promozione<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Es. Saldi autunno" /></label><label>Tipo campagna<select value={form.campaign_type} onChange={(event) => setForm({ ...form, campaign_type: event.target.value })}><option value="PROMOTION">Promozione</option><option value="SALE">Saldi</option></select></label><label>Tipo sconto<select value={form.discount_type} onChange={(event) => setForm({ ...form, discount_type: event.target.value })}><option value="PERCENTAGE">Percentuale</option><option value="FIXED_DISCOUNT">Importo fisso</option></select></label><label>Marca<select value={form.brand} onChange={(event) => setForm({ ...form, brand: event.target.value })}><option value="">Tutto il catalogo</option>{brands.map((brand) => <option key={brand.id} value={brand.id}>{brand.name}</option>)}</select></label><label>{form.discount_type === "PERCENTAGE" ? "Sconto %" : "Sconto €"}<input required type="number" min="0.01" max={form.discount_type === "PERCENTAGE" ? "100" : undefined} step="0.01" value={form.value} onChange={(event) => setForm({ ...form, value: event.target.value })} /></label><label>Inizio<input required type="datetime-local" value={form.valid_from} onChange={(event) => setForm({ ...form, valid_from: event.target.value })} /></label><label>Fine<input required type="datetime-local" value={form.valid_until} onChange={(event) => setForm({ ...form, valid_until: event.target.value })} /></label><label className="promotion-notes">Note<input value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} placeholder="Facoltative" /></label><div className="inline-form-actions"><button type="button" className="secondary-action" onClick={() => setFormOpen(false)}>Annulla</button><button className="primary-action" disabled={saving}>{saving ? "Creazione..." : "Crea e attiva"}</button></div></form>}
    {message && <p className={success ? "operation-success" : "catalog-error"}>{message}</p>}
    <div className="voucher-filters"><div className="products-search"><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Cerca promozione o codice" /></div><div className="status-tabs">{[["ENABLED", "Attive"], ["ENDED", "Terminate"], ["CANCELLED", "Annullate"], ["ALL", "Tutte"]].map(([value, label]) => <button type="button" className={filter === value ? "active" : ""} key={value} onClick={() => setFilter(value)}>{label}</button>)}</div></div>
    <article className="products-list"><div className="promotion-heading"><span>Promozione</span><span>Tipo</span><span>Sconto</span><span>Marca</span><span>Validità</span><span>Stato</span><span>Azioni</span></div>{!data.length ? <div className="empty-product-state"><BadgePercent size={28} /><strong>Nessuna promozione trovata</strong><span>Crea una campagna per applicare sconti automatici alle vendite.</span></div> : data.map(({ campaign, activation, rule, brand }) => <div className="promotion-row" key={campaign.id}><div><strong>{campaign.name}</strong><span>{campaign.code}</span></div><span>{typeLabel[campaign.campaign_type] || campaign.campaign_type}</span><b>{discount(rule)}</b><span>{brand?.name || "Tutto il catalogo"}</span><span>{activation ? `${formatDate(activation.valid_from)} - ${formatDate(activation.valid_until)}` : "Non attivata"}</span><em className={`promotion-status ${(activation?.status || "CANCELLED").toLowerCase()}`}>{activationLabel[activation?.status] || "Non attiva"}</em>{activation?.status === "ENABLED" ? <button className="promotion-end" onClick={() => endPromotion(activation)}><CircleStop size={14} /> Termina</button> : <span>-</span>}</div>)}</article>
  </section>;
}
