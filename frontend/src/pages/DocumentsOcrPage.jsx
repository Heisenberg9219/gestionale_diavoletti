import { useEffect, useMemo, useRef, useState } from "react";
import { Eye, FileText, FileUp, LoaderCircle, Plus, ScanText, Search, Trash2, X } from "lucide-react";
import { request } from "../api";
import PaginatedRows from "../components/PaginatedRows";
import "../products.css";
import "./DocumentsOcrPage.css";

const list = (data) => data?.results || data || [];
async function allPages(path) {
  const rows = [];
  for (let page = 1; ; page += 1) {
    const data = await request(`${path}${path.includes("?") ? "&" : "?"}page=${page}&page_size=200`);
    rows.push(...list(data));
    if (!data.next) return rows;
  }
}
const today = () => new Date().toISOString().slice(0, 10);
const blank = () => ({ document_type: "", title: "", number: "", document_date: today(), counterparty_name: "", file: null });
const directionLabel = { INCOMING: "Ricevuto", OUTGOING: "Emesso", INTERNAL: "Interno" };
const date = (value) => value ? new Intl.DateTimeFormat("it-IT").format(new Date(`${value}T00:00:00`)) : "Non indicata";
const amount = (value) => Number.parseFloat(String(value).replace(",", ".")) || 0;
const money = (value) => amount(value).toFixed(2);
const lineTotal = (item) => amount(item.quantity) * amount(item.unit_price);
const needsReservedSku = (value, committed = false) => !value || /^OCR-\d{3}-\d{3}$/i.test(String(value)) || (!committed && /^SKU-\d+$/i.test(String(value)));
const reviewSkus = (review) => (review?.items || []).flatMap((item) => (item.new_variant?.variants || []).map((variant) => variant.sku).filter(Boolean));

function issueFields(issue) {
  const text = String(issue.message || "").toLocaleLowerCase("it-IT");
  if (text.includes("imponibile fattura deve coincidere")) return ["taxable_amount"];
  if (text.includes("numero fattura")) return ["invoice_number"];
  if (text.includes("fornitore")) return ["supplier_id"];
  if (text.includes("sede")) return ["location_id"];
  if (text.includes("marca predefinita")) return ["brand_id"];
  if (text.includes("tipo collezione")) return ["season_type"];
  if (text.includes("anno collezione")) return ["season_year"];
  if (text.includes("data, imponibile, aliquota iva e totale")) return ["invoice_date", "taxable_amount", "tax_rate", "total_amount"];
  if (text.includes("nome e sku")) return ["product_name", "sku"];
  if (text.includes("nome identico") || text.includes("esiste già un articolo con nome") || text.includes("lunghezza massima")) return ["product_name"];
  if (text.includes("categoria")) return ["category_id"];
  if (text.includes("aliquota iva")) return ["tax_rate_id"];
  if (text.includes("colore")) return ["color_id"];
  if (text.includes("taglia")) return ["size_id"];
  if (text.includes("barcode")) return ["barcode"];
  if (text.includes("sku")) return ["sku"];
  if (text.includes("prezzo vendita")) return ["sale_price"];
  if (text.includes("costo acquisto")) return ["unit_price"];
  if (text.includes("includi almeno una riga")) return ["accepted"];
  if (text.includes("quantità") || text.includes("pezzi")) return ["quantity"];
  return ["variant_id"];
}

function FieldErrors({ issues }) {
  if (!issues.length) return null;
  return <span className="ocr-field-error" role="alert">{issues.map((issue) => issue.message).join(" ")}</span>;
}


function proposalLabel(analysis) {
  const status = analysis.proposed_data?.review?.status;
  const label = ["APPLIED", "IMPORTED"].includes(status) ? "Articoli caricati in magazzino" : status ? "Bozza" : "Scansionato";
  const timestamp = new Date(analysis.created_at);
  const day = timestamp.toLocaleDateString("it-IT");
  const time = timestamp.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  return `${label} del ${day} alle ${time}`;
}

function ocrWorkflowStatus(analysis, attachment) {
  const proposalStatus = analysis?.proposed_data?.review?.status;
  if (["APPLIED", "IMPORTED"].includes(proposalStatus)) return { key: "stock-loaded", label: "Articoli caricati in magazzino" };
  if (proposalStatus === "DRAFT") return { key: "draft", label: "Bozza" };
  if (analysis?.status === "SUCCEEDED") return { key: "scanned", label: "Scansionato" };
  if (analysis?.status === "FAILED") return { key: "failed", label: "OCR non riuscito" };
  return { key: "pending", label: attachment ? "PDF caricato" : "Nessun PDF" };
}

function ocrProcessingLabel(analysis, attachment) {
  if (analysis?.status === "SUCCEEDED") return "OCR completato";
  if (analysis?.status === "FAILED") return "OCR non riuscito";
  return attachment ? "PDF pronto" : "Nessun PDF";
}

function latest(items, attachment) {
  return items.filter((item) => item.attachment === attachment && item.status === "SUCCEEDED").sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0];
}

function makeReview(analysis, catalog = { taxes: [] }, markup = "") {
  const proposal = analysis.proposed_data || {};
  const saved = proposal.review || {};
  const readOnly = ["IMPORTED", "APPLIED"].includes(saved.status);
  const defaultTax = readOnly ? null : catalog.taxes.find((tax) => tax.name?.toLowerCase().includes("ordinaria")) || catalog.taxes.find((tax) => tax.is_default);
  const defaultPrice = (cost) => !readOnly && amount(cost) > 0 && amount(markup) > 0 ? money(amount(cost) * amount(markup)) : "";
  return {
    ...saved,
    supplier_name: saved.supplier_name ?? proposal.supplier_name ?? "",
    invoice_number: saved.invoice_number ?? proposal.invoice_number ?? "",
    invoice_date: saved.invoice_date ?? proposal.invoice_date ?? "",
    supplier_id: saved.supplier_id ?? saved.supplier ?? "",
    location_id: saved.location_id ?? saved.location ?? "",
    brand_id: saved.brand_id ?? "",
    season_type: saved.season_type ?? "",
    season_year: String(saved.season_year ?? new Date().getFullYear()),
    taxable_amount: saved.taxable_amount ?? proposal.taxable_amount ?? "",
    tax_rate: saved.tax_rate !== undefined && saved.tax_rate !== "" ? saved.tax_rate : defaultTax?.percentage ?? "",
    total_amount: saved.total_amount ?? proposal.total_amount ?? "",
    items: (saved.items ?? proposal.items ?? []).map((row, index) => {
      const item = { ...(proposal.items?.[index] || {}), ...row };
      const previous = item.new_product || {};
      const stored = item.new_variant || {};
      return {
        ...item, accepted: item.accepted ?? true,
        variant_id: item.variant_id ?? ((item.new_product || item.new_variant) ? "__new__" : ""),
        description: item.description ?? "", quantity: item.quantity ?? "", unit_price: item.unit_price ?? "", sale_price: item.sale_price || defaultPrice(item.unit_price),
        new_variant: {
          product_id: previous.product_id || "", product_name: previous.name ?? item.description ?? "",
          brand_id: previous.brand || "", category_id: previous.category || "", color_id: previous.color || "", ...stored,
          tax_rate_id: stored.tax_rate_id || previous.tax_rate || defaultTax?.id || "",
          variants: (stored.variants || [{ size_id: stored.size_id || previous.size || "", sku: stored.sku || previous.sku || "", barcode: stored.barcode || previous.barcode || "", quantity: item.quantity ?? "", sale_price: stored.sale_price ?? item.sale_price ?? "" }]).map((variant) => ({ ...variant, sale_price: variant.sale_price || defaultPrice(item.unit_price) })),
        },
      };
    }),
  };
}

export default function DocumentsOcrPage() {
  const [documents, setDocuments] = useState([]); const [types, setTypes] = useState([]); const [attachments, setAttachments] = useState([]); const [analyses, setAnalyses] = useState([]); const [variants, setVariants] = useState([]); const [suppliers, setSuppliers] = useState([]); const [locations, setLocations] = useState([]); const [catalog, setCatalog] = useState({ products: [], brands: [], categories: [], taxes: [], colors: [], sizes: [] }); const [markup, setMarkup] = useState(""); const [documentsLoading, setDocumentsLoading] = useState(true);
  const [query, setQuery] = useState(""); const [formOpen, setFormOpen] = useState(false); const [form, setForm] = useState(blank()); const [saving, setSaving] = useState(false); const [message, setMessage] = useState(""); const [success, setSuccess] = useState(false);
  const [selectedDocuments, setSelectedDocuments] = useState([]); const [deletingDocuments, setDeletingDocuments] = useState(false);
  const [reviewAnalysis, setReviewAnalysis] = useState(null); const [review, setReview] = useState(null); const [reviewSaving, setReviewSaving] = useState(false); const [skuLoading, setSkuLoading] = useState(false); const [reviewAction, setReviewAction] = useState(""); const [reviewError, setReviewError] = useState(""); const [reviewNotice, setReviewNotice] = useState(""); const [validationIssues, setValidationIssues] = useState([]);
  const reviewReferences = useRef(null);
  const proposalVersions = analyses
    .filter((entry) => entry.attachment === reviewAnalysis?.attachment && entry.status === "SUCCEEDED" && entry.proposed_data?.review)
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  const imported = ["IMPORTED", "APPLIED"].includes(review?.status);
  const changeReview = (value) => setReview(value);
  const notice = (text, ok = true) => { setSuccess(ok); setMessage(text); };
  const load = async () => {
    setDocumentsLoading(true);
    const documentRequests = Promise.all([allPages("/documents/documents/"), allPages("/documents/types/?is_active=True"), allPages("/documents/attachments/"), allPages("/documents/ocr-analyses/")]);
    try {
      const [documentData, typeData, attachmentData, analysisData] = await documentRequests;
      setDocuments(list(documentData)); setTypes(list(typeData)); setAttachments(list(attachmentData)); setAnalyses(list(analysisData));
    } catch (error) { notice(`Impossibile caricare i documenti: ${error.message}`, false); }
    finally { setDocumentsLoading(false); }
  };
  const loadReviewReferences = async () => {
    if (reviewReferences.current) return reviewReferences.current;
    const [variantData, supplierData, locationData, productData, brandData, categoryData, taxData, colorData, sizeData, settingsData] = await Promise.all([allPages("/catalog/variants/?page_size=200"), allPages("/suppliers/suppliers/?page_size=200"), allPages("/core/locations/?is_active=True"), allPages("/catalog/products/?is_active=True&page_size=200"), allPages("/catalog/brands/?is_active=True&page_size=200"), allPages("/catalog/categories/?is_active=True&page_size=200"), allPages("/core/tax-rates/?is_active=True&page_size=100"), allPages("/catalog/colors/?is_active=True&page_size=200"), allPages("/catalog/sizes/?is_active=True&page_size=200"), allPages("/core/settings/")]);
    const data = { variants: list(variantData), suppliers: list(supplierData), locations: list(locationData), catalog: { products: list(productData), brands: list(brandData), categories: list(categoryData), taxes: list(taxData), colors: list(colorData), sizes: list(sizeData) }, markup: list(settingsData)[0]?.default_markup || "" };
    reviewReferences.current = data;
    setVariants(data.variants); setSuppliers(data.suppliers); setLocations(data.locations); setCatalog(data.catalog); setMarkup(data.markup);
    return data;
  };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!message) return undefined; const timer = setTimeout(() => setMessage(""), 4000); return () => clearTimeout(timer); }, [message]);

  useEffect(() => {
    if (!reviewNotice) return undefined;
    const timer = setTimeout(() => setReviewNotice(""), 4000);
    return () => clearTimeout(timer);
  }, [reviewNotice]);

  useEffect(() => {
    if (!reviewError) return undefined;
    const timer = setTimeout(() => setReviewError(""), 4000);
    return () => clearTimeout(timer);
  }, [reviewError]);

  const visible = useMemo(() => documents.filter((document) => document.status !== "CANCELLED" && `${document.title} ${document.number} ${document.counterparty_name}`.toLowerCase().includes(query.toLowerCase())), [documents, query]);
  const toggleSelectedDocument = (id) => setSelectedDocuments((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  const toggleAllDocuments = () => setSelectedDocuments((current) => current.length === visible.length ? [] : visible.map((document) => document.id));
  async function deleteSelectedDocuments() {
    if (!selectedDocuments.length || !window.confirm(`Cancellare ${selectedDocuments.length} ${selectedDocuments.length === 1 ? "documento" : "documenti"} selezionati?`)) return;
    setDeletingDocuments(true);
    try {
      const result = await request("/documents/documents/cancel-selected/", { method: "POST", body: JSON.stringify({ document_ids: selectedDocuments }) });
      setSelectedDocuments([]);
      notice(`${result.cancelled} ${result.cancelled === 1 ? "documento cancellato" : "documenti cancellati"} correttamente.`);
      await load();
    } catch (error) { notice(`Impossibile cancellare i documenti: ${error.message}`, false); }
    finally { setDeletingDocuments(false); }
  }
  const typeFor = (id) => types.find((item) => item.id === id);
  const attachmentFor = (documentId) => attachments.filter((item) => item.document === documentId).sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0];
  const analysisForDocument = (documentId) => analyses
    .filter((analysis) => attachments.some((attachment) => attachment.id === analysis.attachment && attachment.document === documentId))
    .sort((a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at))[0];
  const closeReview = () => { if (reviewSaving || skuLoading || reviewAction) return; setReviewAnalysis(null); setReview(null); setReviewError(""); setReviewNotice(""); setValidationIssues([]); };
  async function reserveSkus(count, excludeSkus = []) {
    const result = await request("/catalog/variants/reserve-skus/", { method: "POST", body: JSON.stringify({ count, exclude_skus: excludeSkus }) });
    if (!Array.isArray(result.skus) || result.skus.length !== count) throw new Error("Non è stato possibile generare gli SKU progressivi.");
    return result.skus;
  }
  async function assignReservedSkus(value) {
    const targets = [];
    value.items.forEach((item, itemIndex) => {
      if (item.variant_id !== "__new__") return;
      (item.new_variant.variants || []).forEach((variant, variantIndex) => {
        if (needsReservedSku(variant.sku, value._sku_sequence_committed)) targets.push([itemIndex, variantIndex]);
      });
    });
    if (!targets.length) return value;
    const skus = await reserveSkus(targets.length, reviewSkus(value));
    let skuIndex = 0;
    return { ...value, items: value.items.map((item, itemIndex) => ({ ...item, new_variant: { ...item.new_variant, variants: (item.new_variant.variants || []).map((variant, variantIndex) => {
      const target = targets.some(([targetItem, targetVariant]) => targetItem === itemIndex && targetVariant === variantIndex);
      return target ? { ...variant, sku: skus[skuIndex++] } : variant;
    }) } })) };
  }
  async function openProposal(analysis) {
    setReviewAnalysis(analysis); setReviewError(""); setReviewNotice(""); setValidationIssues([]);
    setReview(makeReview(analysis, catalog, markup)); setReviewAction("Caricamento dei dati per la proposta OCR…"); setSkuLoading(true);
    try {
      const references = await loadReviewReferences();
      const initial = makeReview(analysis, references.catalog, references.markup);
      changeReview(await assignReservedSkus(initial));
    } catch (error) { setReviewError(`Impossibile preparare la proposta: ${error.message}`); }
    finally { setSkuLoading(false); setReviewAction(""); }
  }
  const fieldIssues = (row, field) => validationIssues.filter((issue) => (issue.row ?? null) === row && issueFields(issue).includes(field));
  const updateReview = (key, value) => { setValidationIssues((current) => current.filter((issue) => !((issue.row ?? null) === null && issueFields(issue).includes(key)))); changeReview((current) => ({ ...current, [key]: value })); };
  const updateItem = (index, key, value) => { setValidationIssues((current) => current.filter((issue) => !((issue.row ?? null) === index && issueFields(issue).includes(key)))); changeReview((current) => ({ ...current, items: current.items.map((item, itemIndex) => {
    if (itemIndex !== index) return item;
    const updated = { ...item, [key]: value };
    if (key === "quantity" && item.new_variant.variants.length === 1) {
      updated.new_variant = { ...item.new_variant, variants: [{ ...item.new_variant.variants[0], quantity: value }] };
    }
    if (key === "unit_price" && amount(markup) > 0) {
      const previousPrice = money(amount(item.unit_price) * amount(markup));
      const nextPrice = amount(value) > 0 ? money(amount(value) * amount(markup)) : "";
      updated.sale_price = !item.sale_price || money(item.sale_price) === previousPrice ? nextPrice : item.sale_price;
      updated.new_variant = { ...item.new_variant, variants: item.new_variant.variants.map((variant) => ({ ...variant,
        sale_price: !variant.sale_price || money(variant.sale_price) === previousPrice ? nextPrice : variant.sale_price,
      })) };
    }
    return updated;
  }) })); };
  const updateNewVariant = (index, key, value) => { setValidationIssues((current) => current.filter((issue) => !((issue.row ?? null) === index && issueFields(issue).includes(key)))); changeReview((current) => ({ ...current, items: current.items.map((item, itemIndex) => itemIndex === index ? { ...item, new_variant: { ...item.new_variant, [key]: value } } : item) })); };
  const updateVariantDetail = (itemIndex, variantIndex, key, value) => { setValidationIssues((current) => current.filter((issue) => !((issue.row ?? null) === itemIndex && issueFields(issue).includes(key)))); changeReview((current) => ({ ...current, items: current.items.map((item, index) => index === itemIndex ? { ...item, new_variant: { ...item.new_variant, variants: (item.new_variant.variants || []).map((variant, variantPosition) => variantPosition === variantIndex ? { ...variant, [key]: value } : variant) } } : item) })); };
  const removeReviewItem = (itemIndex) => { setValidationIssues((current) => current.filter((issue) => (issue.row ?? null) !== itemIndex)); changeReview((current) => ({ ...current, items: current.items.filter((_, index) => index !== itemIndex) })); };
  async function chooseVariant(itemIndex, value) {
    updateItem(itemIndex, "variant_id", value);
    if (value !== "__new__") return;
    const missing = (review.items[itemIndex]?.new_variant?.variants || []).filter((variant) => needsReservedSku(variant.sku, review._sku_sequence_committed)).length;
    if (!missing) return;
    setSkuLoading(true);
    try {
      const skus = await reserveSkus(missing, reviewSkus(review)); let skuIndex = 0;
      changeReview((current) => ({ ...current, items: current.items.map((item, index) => index !== itemIndex ? item : { ...item, new_variant: { ...item.new_variant, variants: item.new_variant.variants.map((variant) => needsReservedSku(variant.sku, current._sku_sequence_committed) ? { ...variant, sku: skus[skuIndex++] } : variant) } }) }));
    } catch (error) { setReviewError(`Impossibile generare gli SKU: ${error.message}`); } finally { setSkuLoading(false); }
  }
  async function addVariantSize(itemIndex) {
    setSkuLoading(true);
    try {
      const [sku] = await reserveSkus(1, reviewSkus(review));
      changeReview((current) => ({ ...current, items: current.items.map((item, index) => index === itemIndex ? { ...item, new_variant: { ...item.new_variant, variants: [...(item.new_variant.variants || []), { size_id: "", sku, barcode: "", quantity: "", sale_price: amount(item.unit_price) > 0 && amount(markup) > 0 ? money(amount(item.unit_price) * amount(markup)) : "" }] } } : item) }));
    } catch (error) { setReviewError(`Impossibile generare lo SKU: ${error.message}`); } finally { setSkuLoading(false); }
  }
  const removeVariantSize = (itemIndex, variantIndex) => changeReview((current) => ({ ...current, items: current.items.map((item, index) => index === itemIndex ? { ...item, new_variant: { ...item.new_variant, variants: item.new_variant.variants.filter((_, position) => position !== variantIndex) } } : item) }));
  async function addCategory(itemIndex) { const name = window.prompt("Nome della nuova categoria")?.trim(); if (!name) return; const code = `${name.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 20) || "CATEGORIA"}_${Date.now().toString().slice(-5)}`; try { const category = await request("/catalog/categories/", { method: "POST", body: JSON.stringify({ code, name }) }); setCatalog((current) => ({ ...current, categories: [...current.categories, category] })); updateNewVariant(itemIndex, "category_id", category.id); } catch (error) { setReviewError(error.message); } }
  async function addBrand(itemIndex = null) { const name = window.prompt("Nome della nuova marca")?.trim(); if (!name) return; const code = `${name.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 20) || "MARCA"}_${Date.now().toString().slice(-5)}`; try { const brand = await request("/catalog/brands/", { method: "POST", body: JSON.stringify({ code, name }) }); setCatalog((current) => ({ ...current, brands: [...current.brands, brand] })); if (itemIndex === null) updateReview("brand_id", brand.id); else updateNewVariant(itemIndex, "brand_id", brand.id); } catch (error) { setReviewError(error.message); } }
  async function addColor(itemIndex) { const name = window.prompt("Nome del nuovo colore")?.trim(); if (!name) return; const code = `${name.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 20) || "COLORE"}_${Date.now().toString().slice(-5)}`; try { const color = await request("/catalog/colors/", { method: "POST", body: JSON.stringify({ code, name }) }); setCatalog((current) => ({ ...current, colors: [...current.colors, color] })); updateNewVariant(itemIndex, "color_id", color.id); } catch (error) { setReviewError(error.message); } }
  const reviewSubtotal = review?.items.filter((item) => item.accepted).reduce((total, item) => total + lineTotal(item), 0) || 0;
  const reviewTax = reviewSubtotal * amount(review?.tax_rate) / 100;
  const reviewTotal = reviewSubtotal + reviewTax;
  const recalculateAmounts = async () => {
    setReviewAction("Ricalcolo degli importi in corso…");
    await new Promise((resolve) => window.requestAnimationFrame(resolve));
    try {
      if (!review?.items?.some((item) => item.accepted)) throw new Error("seleziona almeno una riga da includere");
      setValidationIssues((current) => current.filter((issue) => !((issue.row ?? null) === null && ["taxable_amount", "total_amount"].some((field) => issueFields(issue).includes(field)))));
      changeReview((current) => {
        const taxable = current.items.filter((item) => item.accepted).reduce((total, item) => total + lineTotal(item), 0);
        const total = taxable + taxable * amount(current.tax_rate) / 100;
        return { ...current, taxable_amount: money(taxable), total_amount: money(total) };
      });
      setReviewError("");
      setReviewNotice("Importi ricalcolati correttamente dalle righe incluse.");
    } catch (error) {
      setReviewNotice("");
      setReviewError(`Il ricalcolo non è avvenuto: ${error.message}.`);
    } finally { setReviewAction(""); }
  };

  async function upload(event) { event.preventDefault(); if (!form.file) return notice("Seleziona un PDF da allegare.", false); setSaving(true); try { const type = typeFor(form.document_type); const document = await request("/documents/documents/", { method: "POST", body: JSON.stringify({ document_type: form.document_type, direction: type.direction, status: "DRAFT", number: form.number, document_date: form.document_date, title: form.title, taxable_amount: "0.00", tax_amount: "0.00", total_amount: "0.00", counterparty_name: form.counterparty_name }) }); const data = new FormData(); data.append("file", form.file); data.append("description", "Documento caricato per analisi OCR"); await request(`/documents/documents/${document.id}/upload-attachment/`, { method: "POST", body: data }); setFormOpen(false); setForm(blank()); notice("Documento e PDF caricati. Avvia l'OCR per preparare la proposta."); await load(); } catch (error) { notice(error.message, false); } finally { setSaving(false); } }
  async function analyze(attachment) { try { await request(`/documents/attachments/${attachment.id}/analyze-invoice/`, { method: "POST", body: JSON.stringify({}) }); notice("Analisi OCR completata. Apri la proposta per controllare gli articoli."); await load(); } catch (error) { notice(error.message, false); await load(); } }
  const draftReview = () => ({ ...review, supplier: review.supplier_id, location: review.location_id });
  const applyReview = () => ({ ...draftReview(), items: review.items.map((item) => ({ ...item, variant_id: item.variant_id === "__new__" ? "" : item.variant_id, new_variant: item.variant_id === "__new__" ? item.new_variant : undefined })) });
  async function saveDraft() {
    setReviewSaving(true); setReviewAction("Salvataggio della proposta in corso…"); setReviewError(""); setReviewNotice("");
    try {
      const saved = await request(`/documents/ocr-analyses/${reviewAnalysis.id}/save-purchase-proposal/`, { method: "POST", body: JSON.stringify({ review: draftReview() }) });
      setReviewAnalysis(saved); changeReview(makeReview(saved, catalog, markup));
      setReviewNotice("Proposta salvata correttamente. Le giacenze non sono state modificate."); await load();
    } catch (error) { setReviewError(`La bozza non è stata salvata: ${error.message}`); } finally { setReviewSaving(false); setReviewAction(""); }
  }
  async function saveReview() {
    setReviewSaving(true); setReviewAction("Verifica e caricamento degli articoli in magazzino…"); setReviewError(""); setReviewNotice(""); setValidationIssues([]);
    try {
      const proposal = applyReview();
      const validation = await request(`/documents/attachments/${reviewAnalysis.attachment}/validate-review/`, { method: "POST", body: JSON.stringify({ review: proposal }) });
      if (validation.conflicts.length) {
        const issues = validation.issues?.length ? validation.issues : validation.conflicts.map((message) => ({ row: null, kind: "incomplete", message }));
        setValidationIssues(issues);
        setReviewError("Il caricamento in magazzino non è avvenuto: correggi i campi evidenziati.");
        window.setTimeout(() => document.querySelector(".ocr-field-error")?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
        return;
      }
      await request(`/documents/ocr-analyses/${reviewAnalysis.id}/save-purchase-proposal/`, { method: "POST", body: JSON.stringify({ review: draftReview() }) });
      await request(`/documents/ocr-analyses/${reviewAnalysis.id}/apply-purchase-proposal/`, { method: "POST", body: JSON.stringify({ review: proposal, supplier: review.supplier_id, location: review.location_id }) });
      setReviewAnalysis(null); setReview(null); notice("Articoli caricati in magazzino correttamente."); await load();
    } catch (error) { setReviewError(`Il caricamento in magazzino non è avvenuto: ${error.message}`); } finally { setReviewSaving(false); setReviewAction(""); }
  }

  return <section className="products-page documents-page">
    <div className="page-title-row"><div><p className="eyebrow">Gestione</p><h2>Documenti e OCR</h2><span>Carica fatture e documenti PDF, poi verifica gli articoli rilevati.</span></div><button className="primary-action" onClick={() => { setForm(blank()); setFormOpen(true); }}><Plus size={17} /> Carica documento</button></div>
    {formOpen && <form className="document-form" onSubmit={upload}><div className="inventory-form-copy document-copy"><p className="eyebrow">Nuovo documento</p><h3>Carica un PDF</h3><span>L'OCR riconosce i dati della fattura dopo il caricamento.</span></div><label>Tipo documento<select required value={form.document_type} onChange={(event) => setForm({ ...form, document_type: event.target.value })}><option value="">Seleziona tipo</option>{types.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Titolo<input required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label><label>Numero documento<input value={form.number} onChange={(event) => setForm({ ...form, number: event.target.value })} /></label><label>Data documento<input required type="date" value={form.document_date} onChange={(event) => setForm({ ...form, document_date: event.target.value })} /></label><label>Fornitore<input value={form.counterparty_name} onChange={(event) => setForm({ ...form, counterparty_name: event.target.value })} /></label><label>File PDF<span className="document-file-control"><input id="document-pdf" required type="file" accept="application/pdf" onChange={(event) => setForm({ ...form, file: event.target.files?.[0] || null })} /><button type="button" onClick={() => document.getElementById("document-pdf")?.click()}>Scegli file</button><span>{form.file?.name || "Nessun file selezionato"}</span></span></label><div className="inline-form-actions"><button type="button" className="secondary-action" onClick={() => setFormOpen(false)}>Annulla</button><button className="primary-action" disabled={saving}>{saving ? "Caricamento..." : "Carica"}</button></div></form>}
    {message && <p className={success ? "operation-success" : "catalog-error"}>{message}</p>}
    <div className="voucher-filters"><div className="products-search"><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Cerca documento, numero o fornitore" /></div></div>
    {selectedDocuments.length > 0 && <div className="table-selection-actions"><span>{selectedDocuments.length} {selectedDocuments.length === 1 ? "documento selezionato" : "documenti selezionati"}</span><button type="button" onClick={() => setSelectedDocuments([])}>Deseleziona</button><button type="button" className="delete-selected" disabled={deletingDocuments} onClick={deleteSelectedDocuments}><Trash2 size={16} /> {deletingDocuments ? "Cancellazione..." : "Cancella selezionati"}</button></div>}
    <article className="products-list">
      <div className="document-heading"><span className="document-check"><input type="checkbox" aria-label="Seleziona tutti i documenti" checked={visible.length > 0 && selectedDocuments.length === visible.length} onChange={toggleAllDocuments} /></span><span>Documento</span><span>Tipo</span><span>Data</span><span>PDF e OCR</span><span>Stato</span><span>Azioni</span></div>
      {documentsLoading ? <div className="documents-loading" role="status"><LoaderCircle size={28} /><strong>Caricamento documenti in corso…</strong><span>Recupero fatture, allegati e stato OCR.</span></div> : !visible.length ? <div className="empty-product-state"><FileText size={28} /><strong>Nessun documento trovato</strong><span>Carica un PDF per costruire l'archivio documentale.</span></div> : <PaginatedRows items={visible} resetKey={query}>{(rows) => rows.map((document) => {
        const analysis = analysisForDocument(document.id); const attachment = attachments.find((item) => item.id === analysis?.attachment) || attachmentFor(document.id); const workflow = ocrWorkflowStatus(analysis, attachment);
        return <div className={`document-row${selectedDocuments.includes(document.id) ? " selected" : ""}`} key={document.id}>
          <span className="document-check"><input type="checkbox" aria-label={`Seleziona ${document.title}`} checked={selectedDocuments.includes(document.id)} onChange={() => toggleSelectedDocument(document.id)} /></span>
          <div><strong>{document.title}</strong><span>{document.number || "Numero non indicato"}{document.counterparty_name ? ` · ${document.counterparty_name}` : ""}</span></div><span>{typeFor(document.document_type)?.name || directionLabel[document.direction]}</span><span>{date(document.document_date)}</span><span>{ocrProcessingLabel(analysis, attachment)}</span><em className={`document-status ${workflow.key}`}>{workflow.label}</em><div className="document-actions">{analysis?.status === "SUCCEEDED" && <button title="Apri proposta OCR" onClick={() => openProposal(analysis)}><Eye size={16} /></button>}{attachment && <button title="Analizza fattura con OCR" onClick={() => analyze(attachment)}><ScanText size={16} /></button>}{attachment?.file && <a href={attachment.file} target="_blank" rel="noreferrer" title="Apri PDF"><FileUp size={16} /></a>}</div>
        </div>;
      })}</PaginatedRows>}
    </article>
    {reviewAnalysis && review && <div className="ocr-review-layer" role="dialog" aria-modal="true">
      <button className="ocr-review-backdrop" aria-label="Chiudi" onClick={closeReview} />
      <section className="ocr-review-modal">
        {reviewAction && <div className="ocr-review-progress" role="status" aria-live="polite"><LoaderCircle size={34} /><strong>{reviewAction}</strong><span>Attendi: i dati vengono elaborati. Non chiudere questa finestra.</span></div>}
        <header><div><p className="eyebrow">Proposta OCR</p><h3>Controlla e registra la fattura</h3></div><button type="button" title="Chiudi" onClick={closeReview}><X size={20} /></button></header>
        {reviewError && <p className="ocr-review-feedback error" role="alert">{reviewError}</p>}
        {reviewNotice && <p className="ocr-review-feedback success">{reviewNotice}</p>}
        {proposalVersions.length > 1 && <div className="ocr-proposal-history"><label htmlFor="ocr-proposal-version">Versione della proposta</label><select id="ocr-proposal-version" disabled={reviewSaving || skuLoading || reviewAction} value={reviewAnalysis.id} onChange={(event) => { const selected = proposalVersions.find((entry) => entry.id === event.target.value); if (selected) openProposal(selected); }}>{proposalVersions.map((entry, index) => <option key={entry.id} value={entry.id}>{`Versione ${proposalVersions.length - index} · ${proposalLabel(entry)}`}</option>)}</select></div>}
        <fieldset className="ocr-review-fields" disabled={reviewSaving || skuLoading || reviewAction || imported}>
          <div id="ocr-invoice-fields" className="ocr-review-summary">
            <label>Fornitore<input value={review.supplier_name} onChange={(event) => updateReview("supplier_name", event.target.value)} /></label>
            <label className={fieldIssues(null, "supplier_id").length ? "ocr-invalid" : ""}>Fornitore in rubrica<select value={review.supplier_id} onChange={(event) => updateReview("supplier_id", event.target.value)}><option value="">Seleziona fornitore</option>{suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.business_name}</option>)}</select><FieldErrors issues={fieldIssues(null, "supplier_id")} /></label>
            <label className={fieldIssues(null, "location_id").length ? "ocr-invalid" : ""}>Destinazione carico<select value={review.location_id} onChange={(event) => updateReview("location_id", event.target.value)}><option value="">Seleziona sede</option>{locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select><FieldErrors issues={fieldIssues(null, "location_id")} /></label>
            <label className={fieldIssues(null, "invoice_number").length ? "ocr-invalid" : ""}>Numero fattura<input value={review.invoice_number} onChange={(event) => updateReview("invoice_number", event.target.value)} /><FieldErrors issues={fieldIssues(null, "invoice_number")} /></label>
            <label className={fieldIssues(null, "invoice_date").length ? "ocr-invalid" : ""}>Data<input type="date" value={review.invoice_date} onChange={(event) => updateReview("invoice_date", event.target.value)} /><FieldErrors issues={fieldIssues(null, "invoice_date")} /></label>
            <label className={fieldIssues(null, "taxable_amount").length ? "ocr-invalid" : ""}>Imponibile articoli<input inputMode="decimal" value={review.taxable_amount} onChange={(event) => updateReview("taxable_amount", event.target.value)} /><FieldErrors issues={fieldIssues(null, "taxable_amount")} /></label>
            <label className={fieldIssues(null, "tax_rate").length ? "ocr-invalid" : ""}>IVA %<input inputMode="decimal" value={review.tax_rate} onChange={(event) => updateReview("tax_rate", event.target.value)} /><FieldErrors issues={fieldIssues(null, "tax_rate")} /></label>
            <label className={fieldIssues(null, "total_amount").length ? "ocr-invalid" : ""}>Totale fattura<input inputMode="decimal" value={review.total_amount} onChange={(event) => updateReview("total_amount", event.target.value)} /><FieldErrors issues={fieldIssues(null, "total_amount")} /></label>
            <div className="ocr-catalog-defaults"><strong>Dati catalogo per i nuovi articoli</strong><span>Verranno applicati a tutti gli articoli creati da questa fattura.</span></div>
            <label className={fieldIssues(null, "brand_id").length ? "ocr-invalid" : ""}>Marca predefinita<span className="select-with-add"><select value={review.brand_id} onChange={(event) => updateReview("brand_id", event.target.value)}><option value="">Seleziona marca</option>{catalog.brands.map((brand) => <option key={brand.id} value={brand.id}>{brand.name}</option>)}</select><button type="button" onClick={() => addBrand()} title="Aggiungi marca"><Plus size={16} /></button></span><FieldErrors issues={fieldIssues(null, "brand_id")} /></label>
            <label className={fieldIssues(null, "season_type").length ? "ocr-invalid" : ""}>Tipo collezione<select value={review.season_type} onChange={(event) => updateReview("season_type", event.target.value)}><option value="">Seleziona collezione</option><option value="SPRING_SUMMER">Primavera/Estate</option><option value="AUTUMN_WINTER">Autunno/Inverno</option></select><FieldErrors issues={fieldIssues(null, "season_type")} /></label>
            <label className={fieldIssues(null, "season_year").length ? "ocr-invalid" : ""}>Anno collezione<input type="number" min="2000" max="2100" value={review.season_year} onChange={(event) => updateReview("season_year", event.target.value)} /><FieldErrors issues={fieldIssues(null, "season_year")} /></label>
          </div>
          <div className="ocr-review-lines"><div className="ocr-review-heading"><span>Incl.</span><span>Descrizione</span><span>Articolo in catalogo</span><span>Qta</span><span>Costo acquisto</span><span>Totale</span><span /></div>
          {review.items.length ? review.items.map((item, index) => <div key={index} id={`ocr-row-${index}`} className={`ocr-review-row${item.accepted ? "" : " is-discarded"}`}>
            <div className="ocr-review-line">
              <span className={fieldIssues(index, "accepted").length ? "ocr-inclusion ocr-invalid" : "ocr-inclusion"}><label><input type="checkbox" checked={item.accepted} onChange={(event) => updateItem(index, "accepted", event.target.checked)} /><span className="sr-only">Includi articolo</span></label><FieldErrors issues={fieldIssues(index, "accepted")} /></span>
              <input value={item.description} onChange={(event) => updateItem(index, "description", event.target.value)} />
              <span className={fieldIssues(index, "variant_id").length ? "ocr-control ocr-invalid" : "ocr-control"}><select value={item.variant_id} onChange={(event) => chooseVariant(index, event.target.value)}><option value="">Seleziona articolo</option><option value="__new__">Crea articolo e variante</option>{variants.map((variant) => <option value={variant.id} key={variant.id}>{variant.product_name || "Articolo"} · {variant.sku}</option>)}</select><FieldErrors issues={fieldIssues(index, "variant_id")} /></span>
              <span className={fieldIssues(index, "quantity").length ? "ocr-control ocr-invalid" : "ocr-control"}><input inputMode="numeric" value={item.quantity} onChange={(event) => updateItem(index, "quantity", event.target.value)} /><FieldErrors issues={fieldIssues(index, "quantity")} /></span>
              <span className={fieldIssues(index, "unit_price").length ? "ocr-control ocr-invalid" : "ocr-control"}><input inputMode="decimal" value={item.unit_price} onChange={(event) => updateItem(index, "unit_price", event.target.value)} /><FieldErrors issues={fieldIssues(index, "unit_price")} /></span>
              <input readOnly value={money(lineTotal(item))} />
              <button type="button" className="ocr-remove-row" onClick={() => removeReviewItem(index)} title="Elimina riga">×</button>
            </div>
            {item.variant_id && item.variant_id !== "__new__" && <label className={`ocr-item-details${fieldIssues(index, "sale_price").length ? " ocr-invalid" : ""}`}>Prezzo vendita<input inputMode="decimal" value={item.sale_price} onChange={(event) => updateItem(index, "sale_price", event.target.value)} /><FieldErrors issues={fieldIssues(index, "sale_price")} /></label>}
            {item.variant_id === "__new__" && <div className="ocr-new-variant">
              <label>Prodotto esistente<select value={item.new_variant.product_id} onChange={(event) => updateNewVariant(index, "product_id", event.target.value)}><option value="">Crea nuovo prodotto</option>{catalog.products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label>
              {!item.new_variant.product_id && <><label className={fieldIssues(index, "product_name").length ? "ocr-invalid" : ""}>Nome nuovo prodotto<input value={item.new_variant.product_name} onChange={(event) => updateNewVariant(index, "product_name", event.target.value)} /><FieldErrors issues={fieldIssues(index, "product_name")} /></label><label>Marca<span className="select-with-add"><select value={item.new_variant.brand_id || ""} onChange={(event) => updateNewVariant(index, "brand_id", event.target.value)}><option value="">Nessuna</option>{catalog.brands.map((brand) => <option key={brand.id} value={brand.id}>{brand.name}</option>)}</select><button type="button" onClick={() => addBrand(index)} title="Aggiungi marca"><Plus size={16} /></button></span></label><label className={fieldIssues(index, "category_id").length ? "ocr-invalid" : ""}>Categoria<span className="select-with-add"><select value={item.new_variant.category_id} onChange={(event) => updateNewVariant(index, "category_id", event.target.value)}><option value="">Seleziona</option>{catalog.categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select><button type="button" onClick={() => addCategory(index)} title="Aggiungi categoria"><Plus size={16} /></button></span><FieldErrors issues={fieldIssues(index, "category_id")} /></label><label className={fieldIssues(index, "tax_rate_id").length ? "ocr-invalid" : ""}>Aliquota IVA articolo<select value={item.new_variant.tax_rate_id || ""} onChange={(event) => updateNewVariant(index, "tax_rate_id", event.target.value)}><option value="">Seleziona aliquota</option>{catalog.taxes.map((tax) => <option key={tax.id} value={tax.id}>{tax.name}</option>)}</select><FieldErrors issues={fieldIssues(index, "tax_rate_id")} /></label></>}
              <label className={fieldIssues(index, "color_id").length ? "ocr-invalid" : ""}>Colore<span className="select-with-add"><select value={item.new_variant.color_id} onChange={(event) => updateNewVariant(index, "color_id", event.target.value)}><option value="">Nessuno</option>{catalog.colors.map((color) => <option key={color.id} value={color.id}>{color.name}</option>)}</select><button type="button" onClick={() => addColor(index)} title="Aggiungi colore"><Plus size={16} /></button></span><FieldErrors issues={fieldIssues(index, "color_id")} /></label>
              <div className="ocr-variant-sizes"><div className="ocr-variant-sizes-heading"><strong>Taglie e quantità</strong><button type="button" onClick={() => addVariantSize(index)}><Plus size={15} /> Aggiungi taglia</button></div>{(item.new_variant.variants || []).map((variant, variantIndex) => <div className="ocr-variant-size-row" key={variantIndex}>
                <label className={fieldIssues(index, "size_id").length ? "ocr-invalid" : ""}>Taglia<select value={variant.size_id} onChange={(event) => updateVariantDetail(index, variantIndex, "size_id", event.target.value)}><option value="">Seleziona</option>{catalog.sizes.map((size) => <option key={size.id} value={size.id}>{size.size_scale_name} · {size.label}</option>)}</select><FieldErrors issues={fieldIssues(index, "size_id")} /></label>
                <label className={fieldIssues(index, "quantity").length ? "ocr-invalid" : ""}>Quantità<input inputMode="numeric" value={variant.quantity} onChange={(event) => updateVariantDetail(index, variantIndex, "quantity", event.target.value)} />{item.new_variant.variants.length === 1 && amount(variant.quantity) !== amount(item.quantity) && <button type="button" className="ocr-markup-action" onClick={() => updateVariantDetail(index, variantIndex, "quantity", item.quantity)}>Usa quantità riga: {item.quantity}</button>}<FieldErrors issues={fieldIssues(index, "quantity")} /></label>
                <label className={fieldIssues(index, "sku").length ? "ocr-invalid" : ""}>SKU<input value={variant.sku} onChange={(event) => updateVariantDetail(index, variantIndex, "sku", event.target.value)} /><FieldErrors issues={fieldIssues(index, "sku")} /></label>
                <label className={fieldIssues(index, "barcode").length ? "ocr-invalid" : ""}>Codice a barre<input value={variant.barcode || ""} onChange={(event) => updateVariantDetail(index, variantIndex, "barcode", event.target.value)} /><FieldErrors issues={fieldIssues(index, "barcode")} /></label>
                <label className={fieldIssues(index, "sale_price").length ? "ocr-invalid" : ""}>Prezzo vendita<input inputMode="decimal" value={variant.sale_price} onChange={(event) => updateVariantDetail(index, variantIndex, "sale_price", event.target.value)} /><button type="button" className="ocr-markup-action" onClick={() => updateVariantDetail(index, variantIndex, "sale_price", money(amount(item.unit_price) * amount(markup)))}>Applica ricarico</button><FieldErrors issues={fieldIssues(index, "sale_price")} /></label>
                <button type="button" className="ocr-remove-size" disabled={(item.new_variant.variants || []).length === 1} onClick={() => removeVariantSize(index, variantIndex)} title="Rimuovi taglia">×</button>
              </div>)}</div>
            </div>}
          </div>) : <p className="ocr-review-empty">L’OCR non ha riconosciuto righe articolo in questo PDF.</p>}</div>
          <div className="ocr-row-actions"><button type="button" className="secondary-action" onClick={recalculateAmounts}>Ricalcola importi dalle righe incluse</button><button type="button" className="secondary-action" onClick={() => updateReview("items", [...review.items, makeReview({ proposed_data: { items: [{}] } }, catalog, markup).items[0]])}>Aggiungi riga</button></div>
        </fieldset>
        <footer><span><button type="button" className="secondary-action" disabled={reviewSaving || skuLoading || reviewAction || imported} onClick={saveDraft}>Salva proposta</button><button className="primary-action" disabled={reviewSaving || skuLoading || reviewAction || imported} onClick={saveReview}>{skuLoading ? "Generazione SKU..." : "Conferma e carica in magazzino"}</button></span></footer>
      </section>
    </div>}
  </section>;
}
