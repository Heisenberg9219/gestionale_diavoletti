import { useEffect, useRef, useState } from "react";
import { Plus, X } from "lucide-react";
import { request } from "../api";
import "./GiftListDetails.css";
import GiftListCatalogPicker, { variantLabel } from "./GiftListCatalogPicker";

const emptyContribution = () => ({ first_name: "", last_name: "", amount: "", payment_method: "CASH" });
const money = (value) => new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(value);
const statusLabel = { OPEN: "Aperta", CLOSED: "Chiusa", CANCELLED: "Annullata" };
const paymentLabel = { CASH: "Contanti", CARD: "Carta", OTHER: "Altro" };

async function readRows(resource, giftListId) {
  const rows = [];
  for (let page = 1; ; page += 1) {
    const data = await request(`/gift-lists/${resource}/?gift_list=${giftListId}&page_size=200&page=${page}&ordering=created_at`);
    rows.push(...(data.results || data));
    if (!data.next) return rows;
  }
}

export default function GiftListDetails({ giftListId, startAdding = false, onClose }) {
  const [giftList, setGiftList] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [formOpen, setFormOpen] = useState(startAdding);
  const [form, setForm] = useState(emptyContribution);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const dialog = useRef(null);
  const submitting = useRef(false);
  const canAdd = giftList?.mode === "CONTRIBUTIONS" && giftList.status === "OPEN";
  const totalCents = rows.reduce((sum, row) => sum + Math.round(Number(row.amount || 0) * 100), 0);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const detail = await request(`/gift-lists/lists/${giftListId}/`);
        let entries = await readRows(detail.mode === "CONTRIBUTIONS" ? "contributions" : "items", giftListId);
        if (detail.mode === "PRODUCTS") {
          entries = await Promise.all(entries.map(async (entry) => {
            const variant = await request(`/catalog/variants/${entry.variant}/`);
            return { ...entry, label: variantLabel(variant) };
          }));
        }
        if (active) { setGiftList(detail); setRows(entries); }
      } catch (exception) { if (active) setLoadError(exception.message); }
      finally { if (active) setLoading(false); }
    }
    load();
    return () => { active = false; };
  }, [giftListId]);

  useEffect(() => {
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.focus();
    return () => { document.body.style.overflow = previousOverflow; previousFocus?.focus(); };
  }, []);

  useEffect(() => {
    if (!error && !notice) return;
    const timer = setTimeout(() => { setError(""); setNotice(""); }, 4000);
    return () => clearTimeout(timer);
  }, [error, notice]);

  function handleKeys(event) {
    if (event.key === "Escape" && !submitting.current) onClose();
    if (event.key !== "Tab") return;
    const focusable = [...dialog.current.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]')];
    const first = focusable[0]; const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }

  async function addContribution(event) {
    event.preventDefault();
    if (submitting.current || !canAdd) return;
    const payload = { ...form, first_name: form.first_name.trim(), last_name: form.last_name.trim(), amount: form.amount.trim().replace(",", ".") };
    setError(""); setNotice("");
    if (!payload.first_name || !payload.last_name) { setError("Inserisci nome e cognome del conferente."); return; }
    if (!/^\d+(\.\d{1,2})?$/.test(payload.amount) || Number(payload.amount) <= 0) { setError("Inserisci un importo maggiore di zero, con massimo due decimali."); return; }
    submitting.current = true; setSaving(true);
    try {
      const contribution = await request(`/gift-lists/lists/${giftList.id}/add-contribution/`, { method: "POST", body: JSON.stringify(payload) });
      setRows((current) => [...current, contribution]);
      setForm(emptyContribution()); setFormOpen(false); setNotice("Contributo registrato.");
    } catch (exception) { setError(exception.message); }
    finally { submitting.current = false; setSaving(false); }
  }

  async function addArticles(items, variants) {
    if (submitting.current || giftList?.mode !== "PRODUCTS" || giftList.status !== "OPEN") return;
    submitting.current = true; setSaving(true); setError(""); setNotice("");
    try {
      const added = await request(`/gift-lists/lists/${giftList.id}/add-items/`, { method: "POST", body: JSON.stringify({ items }) });
      const labels = new Map(variants.map((variant) => [variant.id, variantLabel(variant)]));
      setRows((current) => [...current, ...added.map((item) => ({ ...item, label: labels.get(item.variant) || "Articolo" }))]);
      setFormOpen(false); setNotice("Articoli aggiunti alla lista.");
    } catch (exception) { setError(exception.message); }
    finally { submitting.current = false; setSaving(false); }
  }

  return <div className="gift-detail-layer">
    <div className="gift-detail-backdrop" onClick={() => { if (!submitting.current) onClose(); }} />
    <section className="gift-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="gift-detail-title" tabIndex={-1} ref={dialog} onKeyDown={handleKeys}>
      <header><div><p className="eyebrow">Lista regalo</p><h3 id="gift-detail-title">{giftList?.title || "Dettaglio lista"}</h3></div><button type="button" className="gift-detail-close" aria-label="Chiudi dettaglio lista" disabled={saving} onClick={onClose}><X size={20} /></button></header>
      {loading ? <p className="gift-detail-loading">Caricamento…</p> : loadError ? <p className="catalog-error" role="alert">{loadError}</p> : <>
        <dl className="gift-detail-summary">
          <div><dt>Beneficiario</dt><dd>{giftList.beneficiary_first_name} {giftList.beneficiary_last_name}</dd></div>
          <div><dt>Modalità</dt><dd>{giftList.mode === "CONTRIBUTIONS" ? "Contributi" : "Articoli"}</dd></div>
          <div><dt>Stato</dt><dd>{statusLabel[giftList.status]}</dd></div>
          <div><dt>Data evento</dt><dd>{giftList.event_date ? new Date(`${giftList.event_date}T00:00:00`).toLocaleDateString("it-IT") : "—"}</dd></div>
        </dl>
        {giftList.notes && <p className="gift-detail-notes">{giftList.notes}</p>}
        {giftList.mode === "CONTRIBUTIONS" ? <>
          <div className="gift-contributions-heading"><div><h4>Conferenti</h4><span>Totale raccolto <strong>{money(totalCents / 100)}</strong></span></div>{canAdd && <button type="button" className="primary-action" disabled={saving} onClick={() => setFormOpen(true)}><Plus size={17} /> Aggiungi conferente</button>}</div>
          {formOpen && canAdd && <form className="gift-contribution-form" onSubmit={addContribution}>
            <label>Nome<input autoFocus required maxLength={120} value={form.first_name} disabled={saving} onChange={(event) => setForm({ ...form, first_name: event.target.value })} /></label>
            <label>Cognome<input required maxLength={120} value={form.last_name} disabled={saving} onChange={(event) => setForm({ ...form, last_name: event.target.value })} /></label>
            <label>Importo (€)<input required inputMode="decimal" placeholder="0,00" value={form.amount} disabled={saving} onChange={(event) => setForm({ ...form, amount: event.target.value })} /></label>
            <label>Pagamento<select value={form.payment_method} disabled={saving} onChange={(event) => setForm({ ...form, payment_method: event.target.value })}>{Object.entries(paymentLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <div className="gift-contribution-actions"><button type="button" className="secondary-action" disabled={saving} onClick={() => { setFormOpen(false); setForm(emptyContribution()); }}>Annulla</button><button className="primary-action" disabled={saving}>{saving ? "Salvataggio…" : "Salva conferente"}</button></div>
          </form>}
          {error && <p className="catalog-error" role="alert">{error}</p>}{notice && <p className="operation-success" role="status">{notice}</p>}
          {rows.length ? <div className="gift-contribution-table"><table><thead><tr><th>Nome</th><th>Cognome</th><th>Pagamento</th><th>Importo</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{row.contributor_first_name}</td><td>{row.contributor_last_name}</td><td>{paymentLabel[row.payment_method]}</td><td>{money(Number(row.amount))}</td></tr>)}</tbody></table></div> : <p className="gift-detail-empty">Nessun conferente registrato.</p>}
        </> : <><div className="gift-contributions-heading"><h4>Articoli della lista</h4>{giftList.status === "OPEN" && <button type="button" className="primary-action" disabled={saving} onClick={() => setFormOpen(true)}><Plus size={17} /> Aggiungi dal catalogo</button>}</div>
          {formOpen && giftList.status === "OPEN" && <GiftListCatalogPicker existingIds={rows.map((item) => item.variant)} saving={saving} onAdd={addArticles} onCancel={() => setFormOpen(false)} />}
          {error && <p className="catalog-error" role="alert">{error}</p>}{notice && <p className="operation-success" role="status">{notice}</p>}
          <div className="gift-contribution-table"><table><thead><tr><th>Articolo</th><th>Richiesti</th><th>Riservati</th><th>Acquistati</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{row.label}</td><td>{row.requested_quantity}</td><td>{row.reserved_quantity}</td><td>{row.purchased_quantity}</td></tr>)}</tbody></table>{!rows.length && <p className="gift-detail-empty">Nessun articolo nella lista.</p>}</div></>}
      </>}
    </section>
  </div>;
}
