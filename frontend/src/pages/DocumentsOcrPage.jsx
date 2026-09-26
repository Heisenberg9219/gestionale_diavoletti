import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Eye, FileText, FileUp, Plus, ScanText, Search, X } from "lucide-react";
import { request } from "../api";
import "../products.css";
import "./DocumentsOcrPage.css";

async function allPages(path) {
  const rows = [];
  let page = 1;
  while (true) {
    const data = await request(`${path}${path.includes("?") ? "&" : "?"}page=${page}&page_size=200`);
    rows.push(...(data.results || data));
    if (!data.next) return rows;
    page += 1;
  }
}
const today = () => new Date().toISOString().slice(0, 10);
const blank = () => ({ document_type: "", title: "", number: "", document_date: today(), counterparty_name: "", file: null });
const statusLabel = { DRAFT: "Bozza", REGISTERED: "Registrato", ISSUED: "Emesso", CANCELLED: "Annullato" };
const directionLabel = { INCOMING: "Ricevuto", OUTGOING: "Emesso", INTERNAL: "Interno" };
const date = (value) => value ? new Intl.DateTimeFormat("it-IT").format(new Date(`${value}T00:00:00`)) : "Non indicata";
const amount = (value) => Number.parseFloat(String(value).replace(",", ".")) || 0;
const money = (value) => amount(value).toFixed(2);
const lineTotal = (item) => amount(item.quantity) * amount(item.unit_price);

function latest(items, attachment) {
  return items.filter((item) => item.attachment === attachment && item.status === "SUCCEEDED").sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0];
}

function makeReview(analysis) {
  const proposal = analysis.proposed_data || {};
  const saved = proposal.review || {};
  return {
    ...saved,
    supplier: saved.supplier ?? "", location: saved.location ?? "",
    supplier_name: saved.supplier_name ?? proposal.supplier_name ?? "",
    invoice_number: saved.invoice_number ?? proposal.invoice_number ?? "",
    invoice_date: saved.invoice_date ?? proposal.invoice_date ?? "",
    taxable_amount: saved.taxable_amount ?? proposal.taxable_amount ?? "",
    tax_rate: saved.tax_rate ?? "",
    total_amount: saved.total_amount ?? proposal.total_amount ?? "",
    items: (saved.items ?? proposal.items ?? []).map((row, index) => { const item = { ...(proposal.items?.[index] || {}), ...row }; return ({
      ...item, accepted: item.accepted ?? true, variant_id: item.variant_id ?? "",
      description: item.description ?? "", quantity: item.quantity ?? "",
      unit_price: item.unit_price ?? "", sale_price: item.sale_price ?? "",
      new_product: item.new_product ?? { name: item.description ?? "", category: "", tax_rate: "", size: "", color: "", sku: "", barcode: "" },
    }); }),
  };
}

export default function DocumentsOcrPage() {
  const [documents, setDocuments] = useState([]); const [types, setTypes] = useState([]); const [attachments, setAttachments] = useState([]); const [analyses, setAnalyses] = useState([]); const [variants, setVariants] = useState([]);
  const [query, setQuery] = useState(""); const [formOpen, setFormOpen] = useState(false); const [form, setForm] = useState(blank()); const [saving, setSaving] = useState(false); const [message, setMessage] = useState(""); const [success, setSuccess] = useState(false);
  const [reviewAnalysis, setReviewAnalysis] = useState(null); const [review, setReview] = useState(null); const [reviewSaving, setReviewSaving] = useState(false);
  const [choices, setChoices] = useState({});
  const [conflicts, setConflicts] = useState([]);
  const [checking, setChecking] = useState(true);
  const [reviewError, setReviewError] = useState("");
  const imported = review?.status === "IMPORTED";
  const notice = (text, ok = true) => { setSuccess(ok); setMessage(text); };
  const load = async () => { try {
    const paths = ["/documents/documents/", "/documents/types/?is_active=True", "/documents/attachments/", "/documents/ocr-analyses/", "/catalog/variants/"];
    const [a,b,c,d,e] = await Promise.all(paths.map(allPages));
    setDocuments(a); setTypes(b); setAttachments(c); setAnalyses(d); setVariants(e);
    const keys = ["supplier", "location", "category", "tax_rate", "size", "color"];
    const urls = ["/suppliers/suppliers/", "/core/locations/", "/catalog/categories/", "/core/tax-rates/", "/catalog/sizes/", "/catalog/colors/"];
    const values = await Promise.all(urls.map((url) => allPages(`${url}?is_active=True`)));
    setChoices(Object.fromEntries(keys.map((key, i) => [key, values[i]])));
  } catch (error) { notice(error.message, false); } };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!message) return undefined; const timer = setTimeout(() => setMessage(""), 4000); return () => clearTimeout(timer); }, [message]);
  const visible = useMemo(() => documents.filter((document) => `${document.title} ${document.number} ${document.counterparty_name}`.toLowerCase().includes(query.toLowerCase())), [documents, query]);
  const typeFor = (id) => types.find((item) => item.id === id); const attachmentFor = (id) => attachments.find((item) => item.document === id);
  const closeReview = () => { if (reviewSaving) return; setReviewAnalysis(null); setReview(null); };
  const updateReview = (key, value) => { setChecking(true); setReview((current) => ({ ...current, [key]: value })); };
  const updateItem = (index, key, value) => { setChecking(true); setReview((current) => ({ ...current, items: current.items.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item) })); };

  useEffect(() => {
    if (!review || imported) return;
    let active = true;
    setChecking(true);
    const timer = setTimeout(async () => {
      try {
        const result = await request(`/documents/attachments/${reviewAnalysis.attachment}/validate-review/`, { method: "POST", body: JSON.stringify({ review }) });
        if (active) { setConflicts(result.conflicts); setChecking(false); }
      } catch (error) { if (active) { setConflicts([error.message]); setChecking(false); } }
    }, 350);
    return () => { active = false; clearTimeout(timer); };
  }, [review, reviewAnalysis, imported]);
  const selectOptions = (key) => <><option value="">Seleziona</option>{(choices[key] || []).map((option) => <option key={option.id} value={option.id}>{option.business_name || option.name || option.label}</option>)}</>;


  async function upload(event) { event.preventDefault(); if (!form.file) return notice("Seleziona un PDF da allegare.", false); setSaving(true); try { const type = typeFor(form.document_type); const document = await request("/documents/documents/", { method: "POST", body: JSON.stringify({ document_type: form.document_type, direction: type.direction, status: "DRAFT", number: form.number, document_date: form.document_date, title: form.title, taxable_amount: "0.00", tax_amount: "0.00", total_amount: "0.00", counterparty_name: form.counterparty_name }) }); const data = new FormData(); data.append("file", form.file); data.append("description", "Documento caricato per analisi OCR"); await request(`/documents/documents/${document.id}/upload-attachment/`, { method: "POST", body: data }); setFormOpen(false); setForm(blank()); notice("Documento e PDF caricati. Avvia l'OCR per preparare la proposta."); await load(); } catch (error) { notice(error.message, false); } finally { setSaving(false); } }
  async function analyze(attachment) { try { await request(`/documents/attachments/${attachment.id}/analyze-invoice/`, { method: "POST", body: JSON.stringify({}) }); notice("Analisi OCR completata. Apri la proposta per controllare gli articoli."); await load(); } catch (error) { notice(error.message, false); await load(); } }
  async function finalize(document) { try { await request(`/documents/documents/${document.id}/finalize/`, { method: "POST", body: JSON.stringify({ number: document.number }) }); notice("Documento registrato correttamente."); await load(); } catch (error) { notice(error.message, false); } }
  async function saveReview(importNow = false) {
    setReviewSaving(true); setReviewError("");
    try {
      const saved = await request(`/documents/attachments/${reviewAnalysis.attachment}/save-review/`, { method: "POST", body: JSON.stringify({ analysis_id: reviewAnalysis.id, review }) });
      setReviewAnalysis(saved); setReview(makeReview(saved));
      if (importNow) {
        await request(`/documents/attachments/${reviewAnalysis.attachment}/import-to-inventory/`, { method: "POST", body: JSON.stringify({ analysis_id: reviewAnalysis.id }) });
        setReviewAnalysis(null); setReview(null);
      }
      notice(importNow ? "Ricezione confermata: Catalogo e Magazzino aggiornati." : "Proposta salvata. Le giacenze non sono state modificate.");
      await load();
    } catch (error) { setReviewError(error.message); } finally { setReviewSaving(false); }
  }

  return <section className="products-page documents-page">
    <div className="page-title-row"><div><p className="eyebrow">Gestione</p><h2>Documenti e OCR</h2><span>Carica fatture e documenti PDF, poi verifica gli articoli rilevati.</span></div><button className="primary-action" onClick={() => { setForm(blank()); setFormOpen(true); }}><Plus size={17} /> Carica documento</button></div>
    {formOpen && <form className="document-form" onSubmit={upload}><div className="inventory-form-copy document-copy"><p className="eyebrow">Nuovo documento</p><h3>Carica un PDF</h3><span>L'OCR riconosce i dati della fattura dopo il caricamento.</span></div><label>Tipo documento<select required value={form.document_type} onChange={(event) => setForm({ ...form, document_type: event.target.value })}><option value="">Seleziona tipo</option>{types.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Titolo<input required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label><label>Numero documento<input value={form.number} onChange={(event) => setForm({ ...form, number: event.target.value })} /></label><label>Data documento<input required type="date" value={form.document_date} onChange={(event) => setForm({ ...form, document_date: event.target.value })} /></label><label>Fornitore<input value={form.counterparty_name} onChange={(event) => setForm({ ...form, counterparty_name: event.target.value })} /></label><label>File PDF<span className="document-file-control"><input id="document-pdf" required type="file" accept="application/pdf" onChange={(event) => setForm({ ...form, file: event.target.files?.[0] || null })} /><button type="button" onClick={() => document.getElementById("document-pdf")?.click()}>Scegli file</button><span>{form.file?.name || "Nessun file selezionato"}</span></span></label><div className="inline-form-actions"><button type="button" className="secondary-action" onClick={() => setFormOpen(false)}>Annulla</button><button className="primary-action" disabled={saving}>{saving ? "Caricamento..." : "Carica"}</button></div></form>}
    {message && <p className={success ? "operation-success" : "catalog-error"}>{message}</p>}
    <div className="voucher-filters"><div className="products-search"><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Cerca documento, numero o fornitore" /></div></div>
    <article className="products-list"><div className="document-heading"><span>Documento</span><span>Tipo</span><span>Data</span><span>PDF e OCR</span><span>Stato</span><span>Azioni</span></div>{!visible.length ? <div className="empty-product-state"><FileText size={28} /><strong>Nessun documento trovato</strong><span>Carica un PDF per costruire l'archivio documentale.</span></div> : visible.map((document) => { const attachment = attachmentFor(document.id); const analysis = attachment && latest(analyses, attachment.id); const reviewed = Boolean(analysis?.proposed_data?.review?.status); return <div className="document-row" key={document.id}><div><strong>{document.title}</strong><span>{document.number || "Numero non indicato"}{document.counterparty_name ? ` · ${document.counterparty_name}` : ""}</span></div><span>{typeFor(document.document_type)?.name || directionLabel[document.direction]}</span><span>{date(document.document_date)}</span><span>{analysis?.status === "SUCCEEDED" ? reviewed ? analysis.proposed_data.review.status === "IMPORTED" ? "Caricato in magazzino" : "Proposta salvata" : "OCR completato" : analysis?.status === "FAILED" ? "OCR non disponibile" : attachment ? "PDF pronto" : "Nessun PDF"}</span><em className={`document-status ${document.status.toLowerCase()}`}>{statusLabel[document.status] || document.status}</em><div className="document-actions">{analysis?.status === "SUCCEEDED" && <button title="Apri proposta OCR" onClick={() => { setReviewError(""); setChecking(true); setReviewAnalysis(analysis); setReview(makeReview(analysis)); }}><Eye size={16} /></button>}{attachment && <button title="Analizza fattura con OCR" onClick={() => analyze(attachment)}><ScanText size={16} /></button>}{document.status === "DRAFT" && reviewed && <button title="Registra documento" onClick={() => finalize(document)}><CheckCircle2 size={16} /></button>}{attachment?.file && <a href={attachment.file} target="_blank" rel="noreferrer" title="Apri PDF"><FileUp size={16} /></a>}</div></div>; })}</article>
    {reviewAnalysis && review && <div className="ocr-review-layer" role="dialog" aria-modal="true"><button className="ocr-review-backdrop" aria-label="Chiudi" onClick={closeReview} /><section className="ocr-review-modal"><header><div><p className="eyebrow">Proposta OCR</p><h3>Controlla gli articoli della fattura</h3><span>Associa una variante del catalogo oppure completa i dati di un nuovo articolo.</span></div><button type="button" title="Chiudi" onClick={closeReview}><X size={20} /></button></header>{reviewError && <p className="catalog-error" role="alert">{reviewError}</p>}<label className="ocr-conflicts">Versione proposta<select disabled={reviewSaving} value={reviewAnalysis.id} onChange={(event) => { const selected = analyses.find((entry) => entry.id === event.target.value); setReviewError(""); setChecking(true); setReviewAnalysis(selected); setReview(makeReview(selected)); }}>{analyses.filter((entry) => entry.attachment === reviewAnalysis.attachment && entry.status === "SUCCEEDED").map((entry) => <option key={entry.id} value={entry.id}>{new Date(entry.created_at).toLocaleString("it-IT")} · {entry.proposed_data?.review?.status || "OCR"}</option>)}</select></label><fieldset disabled={reviewSaving || imported} className="ocr-review-fields"><div className="ocr-review-summary"><label>Fornitore registrato<select value={review.supplier} onChange={(event) => updateReview("supplier", event.target.value)}>{selectOptions("supplier")}</select></label><label>Sede / magazzino<select value={review.location} onChange={(event) => updateReview("location", event.target.value)}>{selectOptions("location")}</select></label><label>Fornitore<input value={review.supplier_name} onChange={(event) => updateReview("supplier_name", event.target.value)} /></label><label>Numero fattura<input value={review.invoice_number} onChange={(event) => updateReview("invoice_number", event.target.value)} /></label><label>Data<input type="date" value={review.invoice_date} onChange={(event) => updateReview("invoice_date", event.target.value)} /></label><label>Imponibile articoli<input inputMode="decimal" value={review.taxable_amount} onChange={(event) => updateReview("taxable_amount", event.target.value)} /></label><label>IVA<input inputMode="decimal" value={review.tax_rate} onChange={(event) => updateReview("tax_rate", event.target.value)} /></label><label>Totale fattura<input inputMode="decimal" value={review.total_amount} onChange={(event) => updateReview("total_amount", event.target.value)} /></label></div><div className="ocr-review-lines"><div className="ocr-review-heading"><span>Incl.</span><span>Descrizione</span><span>Articolo in catalogo</span><span>Qta</span><span>Costo acquisto</span><span>Totale</span></div>{review.items.length ? review.items.map((item, index) => <div className={`ocr-review-line${item.accepted ? "" : " is-discarded"}`} key={index}><label><input type="checkbox" checked={item.accepted} onChange={(event) => updateItem(index, "accepted", event.target.checked)} /><span className="sr-only">Includi articolo</span></label><input value={item.description} onChange={(event) => updateItem(index, "description", event.target.value)} /><select value={item.variant_id} onChange={(event) => updateItem(index, "variant_id", event.target.value)}><option value="">Crea un nuovo articolo</option>{variants.map((variant) => <option value={variant.id} key={variant.id}>{variant.product_name || "Articolo"} · {variant.sku}</option>)}</select><input inputMode="numeric" value={item.quantity} onChange={(event) => updateItem(index, "quantity", event.target.value)} /><input inputMode="decimal" value={item.unit_price} onChange={(event) => updateItem(index, "unit_price", event.target.value)} /><input readOnly value={money(lineTotal(item))} /><div className="ocr-item-details"><label>Prezzo vendita<input inputMode="decimal" value={item.sale_price} onChange={(event) => updateItem(index, "sale_price", event.target.value)} /></label>{!item.variant_id && <>{[ ["name", "Nome articolo"], ["sku", "SKU"], ["barcode", "Barcode (facoltativo)"] ].map(([key, label]) => <label key={key}>{label}<input value={item.new_product[key] || ""} onChange={(event) => updateItem(index, "new_product", { ...item.new_product, [key]: event.target.value })} /></label>)}{[["category", "Categoria"], ["tax_rate", "Aliquota IVA articolo"], ["size", "Taglia"], ["color", "Colore (facoltativo)"]].map(([key, label]) => <label key={key}>{label}<select value={item.new_product[key] || ""} onChange={(event) => updateItem(index, "new_product", { ...item.new_product, [key]: event.target.value })}>{selectOptions(key)}</select></label>)}</>}</div></div>) : <p className="ocr-review-empty">L’OCR non ha riconosciuto righe articolo in questo PDF.</p>}</div><button type="button" className="secondary-action" onClick={() => updateReview("items", [...review.items, { accepted: true, description: "", quantity: "", unit_price: "", sale_price: "", variant_id: "", new_product: {} }])}>Aggiungi riga</button></fieldset><div className="ocr-conflicts" aria-live="polite">{imported ? <p>Proposta già caricata in magazzino.</p> : checking ? <p>Verifica dati e duplicati…</p> : conflicts.length ? <><strong>Dati da completare o conflitti da risolvere</strong><ul>{conflicts.map((error, index) => <li key={index}>{error}</li>)}</ul></> : <p>Dati completi, nessun conflitto rilevato.</p>}</div><footer><p>Salva la proposta per riprenderla in seguito. La conferma crea gli articoli e carica le quantità nella sede selezionata.</p><span><button type="button" className="secondary-action" disabled={reviewSaving || imported} onClick={() => saveReview(false)}>Salva proposta</button><button className="primary-action" disabled={reviewSaving || imported || checking || conflicts.length > 0} onClick={() => saveReview(true)}>Conferma e carica in magazzino</button></span></footer></section></div>}
  </section>;
}
