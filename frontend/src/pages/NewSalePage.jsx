import { useEffect, useRef, useState } from "react";
import { Barcode, Minus, Plus, Search, ShoppingCart, Trash2, X } from "lucide-react";
import { request } from "../api";
import "../new-sale.css";

const euro = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
const list = (payload) => payload.results || payload || [];

export default function NewSalePage({ onNavigate }) {
  const [session, setSession] = useState(null);
  const [register, setRegister] = useState(null);
  const [sale, setSale] = useState(null);
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState([]);
  const [labels, setLabels] = useState({});
  const [message, setMessage] = useState("");
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState("CASH");
  const [paymentAmount, setPaymentAmount] = useState("");
  const [roundedTotal, setRoundedTotal] = useState("");
  const [cashReceived, setCashReceived] = useState("");
  const [paymentReference, setPaymentReference] = useState("");
  const [paymentError, setPaymentError] = useState("");
  const [paying, setPaying] = useState(false);
  const [customerOpen, setCustomerOpen] = useState(false);
  const [customerQuery, setCustomerQuery] = useState("");
  const [customers, setCustomers] = useState([]);
  const [customerLoading, setCustomerLoading] = useState(false);
  const [customerError, setCustomerError] = useState("");
  const [customerMore, setCustomerMore] = useState(false);
  const [customerSaving, setCustomerSaving] = useState(false);
  const customerRequest = useRef(0);
  const customerTimer = useRef(null);
  const customerSubmitting = useRef(false);
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [giftListOpen, setGiftListOpen] = useState(false);
  const [giftLists, setGiftLists] = useState([]);
  const [selectedGiftList, setSelectedGiftList] = useState(null);
  const [giftItems, setGiftItems] = useState([]);
  const [giftLoading, setGiftLoading] = useState(false);
  const [voucherCode, setVoucherCode] = useState("");
  const [voucherMessage, setVoucherMessage] = useState("");
  const [reservedPrompt, setReservedPrompt] = useState(null);
  const [reservedChoice, setReservedChoice] = useState("");
  const [reservedError, setReservedError] = useState("");
  const [adding, setAdding] = useState(false);
  const addingRef = useRef(false);
  const inputRef = useRef(null);

  useEffect(() => {
    Promise.all([request("/sales/sessions/"), request("/sales/registers/")]).then(([sessions, registers]) => {
      const open = list(sessions).find((item) => item.status === "OPEN");
      setSession(open || null);
      setRegister(list(registers).find((item) => item.id === open?.cash_register) || null);
    }).catch(() => setMessage("Non è stato possibile verificare la sessione di cassa."));
  }, []);

  async function ensureSale() {
    if (sale) return sale;
    const created = await request("/sales/sales/", { method: "POST", body: JSON.stringify({ location: register.location, cash_session: session.id, customer: selectedCustomer?.id || null }) });
    setSale(created);
    return created;
  }

  async function search(event) {
    event?.preventDefault();
    if (!query.trim()) return;
    setMessage("");
    try {
      const found = list(await request(`/catalog/variants/?search=${encodeURIComponent(query.trim())}`));
      setMatches(found);
      if (found.length === 1) await addVariant(found[0]);
    } catch { setMessage("Ricerca articolo non disponibile."); }
  }

  async function addVariant(variant, pending = null) {
    if (addingRef.current) return;
    addingRef.current = true; setAdding(true); setReservedError(""); setMessage("");
    try {
      const currentSale = pending?.sale || await ensureSale();
      const existing = currentSale.lines?.find((line) => line.variant === variant.id);
      const previous = pending?.previous ?? (existing?.quantity || 0);
      const result = await request(`/sales/sales/${currentSale.id}/add-with-gift-check/`, {
        method: "POST", body: JSON.stringify({ variant: variant.id, quantity: previous + 1,
          previous_quantity: previous, ...(pending ? { release_item: reservedChoice } : {}) }),
      });
      if (result.confirmation_required) {
        setReservedPrompt({ variant, sale: currentSale, previous, lists: result.lists });
        setReservedChoice(result.lists.length === 1 ? result.lists[0].item : "");
        return;
      }
      setReservedPrompt(null);
      const refreshed = await request(`/sales/sales/${currentSale.id}/`);
      setSale(refreshed);
      setLabels((current) => ({ ...current, [variant.id]: variant.product_name
        ? `${variant.product_name} · ${variant.color_name || ""} ${variant.size_label || ""}`.trim()
        : current[variant.id] || variant.sku || "Articolo" }));
      setMatches([]); setQuery(""); inputRef.current?.focus();
    } catch (err) { if (pending) setReservedError(err.message); else setMessage(err.message); }
    finally { addingRef.current = false; setAdding(false); }
  }

  async function changeQuantity(line, delta) {
    if (addingRef.current) return;
    if (delta > 0 && !line.gift_list_item) return addVariant({ id: line.variant, sku: line.sku_snapshot });
    if (line.quantity + delta < 1) return removeLine(line);
    try {
      await request(`/sales/sales/${sale.id}/set-line/`, { method: "POST", body: JSON.stringify({ variant: line.variant, quantity: line.quantity + delta, gift_list_item: line.gift_list_item || null }) });
      setSale(await request(`/sales/sales/${sale.id}/`));
    } catch (err) { setMessage(err.message); }
  }
  async function removeLine(line) {
    try {
      await request(`/sales/sales/${sale.id}/remove-line/`, { method: "POST", body: JSON.stringify({ line: line.id, reason: "Articolo rimosso dal carrello" }) });
      setSale(await request(`/sales/sales/${sale.id}/`));
      setMessage("Articolo rimosso dal carrello.");
    } catch (err) { setMessage(`Impossibile rimuovere l'articolo: ${err.message}`); }
  }
  useEffect(() => {
    if (!customerOpen) return;
    setCustomerLoading(true); setCustomerError(""); setCustomers([]); setCustomerMore(false);
    customerTimer.current = setTimeout(() => searchCustomers(customerQuery), 250);
    return () => { clearTimeout(customerTimer.current); customerRequest.current += 1; };
  }, [customerOpen, customerQuery]);

  async function searchCustomers(value = customerQuery) {
    clearTimeout(customerTimer.current);
    const requestId = ++customerRequest.current;
    setCustomerLoading(true); setCustomerError(""); setCustomers([]); setCustomerMore(false);
    try {
      const result = await request(`/customers/customers/?search=${encodeURIComponent(value.trim())}&ordering=last_name,first_name&page_size=50`);
      if (requestId === customerRequest.current) { setCustomers(list(result)); setCustomerMore(Boolean(result.next)); }
    } catch (error) {
      if (requestId === customerRequest.current) setCustomerError(`Ricerca clienti non disponibile: ${error.message}`);
    } finally { if (requestId === customerRequest.current) setCustomerLoading(false); }
  }
  async function selectCustomer(customer) {
    if (customerSubmitting.current) return;
    customerSubmitting.current = true; setCustomerSaving(true); setCustomerError("");
    try {
      if (sale) setSale(await request(`/sales/sales/${sale.id}/set-customer/`, { method: "POST", body: JSON.stringify({ customer: customer.id }) }));
      setSelectedCustomer(customer); setCustomerOpen(false); setMessage(`Cliente associato: ${customer.full_name}.`);
    } catch (error) { setCustomerError(`Impossibile associare il cliente: ${error.message}`); }
    finally { customerSubmitting.current = false; setCustomerSaving(false); }
  }
  async function openGiftLists() {
    setGiftListOpen(true); setSelectedGiftList(null); setGiftItems([]); setGiftLoading(true);
    try { setGiftLists(list(await request("/gift-lists/lists/?status=OPEN&mode=PRODUCTS"))); }
    catch (error) { setMessage(`Impossibile caricare le liste regalo: ${error.message}`); }
    finally { setGiftLoading(false); }
  }
  async function selectGiftList(giftList) {
    setSelectedGiftList(giftList); setGiftLoading(true);
    try {
      const [items, variants] = await Promise.all([request(`/gift-lists/items/?gift_list=${giftList.id}`), request("/catalog/variants/?page_size=200")]);
      const variantsById = Object.fromEntries(list(variants).map((variant) => [variant.id, variant]));
      setGiftItems(list(items).map((item) => ({ ...item, variant_data: variantsById[item.variant] })));
    } catch (error) { setMessage(`Impossibile caricare gli articoli della lista: ${error.message}`); }
    finally { setGiftLoading(false); }
  }
  async function addGiftItem(item) {
    const quantity = Number(item.reserved_quantity || 0) - Number(item.purchased_quantity || 0);
    if (quantity < 1) return setMessage("Questa riga della lista è già stata acquistata.");
    try {
      const currentSale = await ensureSale();
      const existing = currentSale.lines?.find((line) => line.variant === item.variant);
      await request(`/sales/sales/${currentSale.id}/set-line/`, { method: "POST", body: JSON.stringify({ variant: item.variant, quantity: (existing?.quantity || 0) + quantity, gift_list_item: item.id }) });
      setSale(await request(`/sales/sales/${currentSale.id}/`));
      setLabels((current) => ({ ...current, [item.variant]: `${item.variant_data?.product_name || "Articolo lista"} · ${item.variant_data?.color_name || ""} ${item.variant_data?.size_label || ""}`.trim() }));
      setMessage(`Articolo della lista ${selectedGiftList.code} aggiunto al carrello.`);
    } catch (error) { setMessage(`Impossibile aggiungere l'articolo della lista: ${error.message}`); }
  }

  const paymentTotal = (currentSale) => Number(currentSale?.final_total_amount || 0) - (currentSale?.payments || []).reduce((total, payment) => total + Number(payment.amount || 0), 0);
  async function openPayment() {
    try {
      const currentSale = await request(`/sales/sales/${sale.id}/`);
      const remaining = Math.max(0, paymentTotal(currentSale));
      setRoundedTotal(Number(currentSale.final_total_amount).toFixed(2));
      setSale(currentSale); setPaymentMethod("CASH"); setPaymentAmount(remaining.toFixed(2)); setCashReceived(remaining.toFixed(2)); setPaymentReference(""); setPaymentError(""); setPaymentOpen(true);
    } catch (error) { setMessage(`Impossibile preparare il pagamento: ${error.message}`); }
  }
  async function applyVoucher() {
    const code = voucherCode.trim().toUpperCase();
    if (!code) return setVoucherMessage("Inserisci il codice del buono.");
    setPaying(true);
    try {
      const vouchers = list(await request(`/vouchers/vouchers/?search=${encodeURIComponent(code)}&status=ACTIVE`));
      const voucher = vouchers.find((item) => item.code?.toUpperCase() === code);
      if (!voucher) return setVoucherMessage("Buono non trovato o non utilizzabile.");
      const remaining = Math.max(0, paymentTotal(sale));
      await request(`/vouchers/vouchers/${voucher.id}/redeem/`, { method: "POST", body: JSON.stringify({ sale: sale.id, amount: remaining.toFixed(2) }) });
      const refreshed = await request(`/sales/sales/${sale.id}/`);
      const newRemaining = Math.max(0, paymentTotal(refreshed));
      setSale(refreshed); setPaymentAmount(newRemaining.toFixed(2)); setCashReceived(newRemaining.toFixed(2)); setVoucherCode(""); setVoucherMessage(`Buono applicato: ${euro.format(Math.min(Number(voucher.current_balance || 0), remaining))}.`);
    } catch (error) { setVoucherMessage(`Impossibile applicare il buono: ${error.message}`); }
    finally { setPaying(false); }
  }
  async function applyRounding() {
    const value = roundedTotal.trim();
    const total = Number(value.replace(",", "."));
    if (!/^\d+(?:[.,]\d{1,2})?$/.test(value) || !Number.isFinite(total) || total < 0) {
      return setPaymentError("Inserisci un totale arrotondato valido, con al massimo due decimali.");
    }
    setPaying(true); setPaymentError("");
    try {
      const updated = await request(`/sales/sales/${sale.id}/set-total/`, { method: "POST", body: JSON.stringify({ final_total_amount: total.toFixed(2), reason: "Arrotondamento al pagamento" }) });
      setSale(updated); setRoundedTotal(Number(updated.final_total_amount).toFixed(2));
      const remaining = Math.max(0, paymentTotal(updated)).toFixed(2);
      setPaymentAmount(remaining); setCashReceived(remaining);
    } catch (error) { setPaymentError(`Impossibile applicare l'arrotondamento: ${error.message}`); }
    finally { setPaying(false); }
  }
  async function completePayment() {
    const amount = Number(String(paymentAmount).replace(",", "."));
    const received = Number(String(cashReceived).replace(",", "."));
    if (!Number.isFinite(amount) || amount < 0) return setPaymentError("Inserisci un importo di pagamento valido.");
    if (amount === 0 && paymentTotal(sale) > 0) return setPaymentError("Inserisci un importo di pagamento valido.");
    if (paymentMethod === "CASH" && (!Number.isFinite(received) || received < amount)) return setPaymentError("Per i contanti indica un importo ricevuto almeno pari al totale.");
    setPaying(true); setPaymentError("");
    try {
      if (amount > 0) await request(`/sales/sales/${sale.id}/add-payment/`, { method: "POST", body: JSON.stringify({ method: paymentMethod, amount: amount.toFixed(2), cash_received_amount: paymentMethod === "CASH" ? received.toFixed(2) : undefined, transaction_reference: paymentReference }) });
      const confirmed = await request(`/sales/sales/${sale.id}/confirm/`, { method: "POST", body: JSON.stringify({}) });
      setPaymentOpen(false); setSale(null); setLabels({}); setMessage(`Vendita ${confirmed.number} registrata correttamente.`); inputRef.current?.focus();
    } catch (error) { setPaymentError(`Pagamento non completato: ${error.message}`); }
    finally { setPaying(false); }
  }

  if (!session || !register) return <section className="new-sale-empty">
<Barcode size={28} />
<h2>Apri prima la cassa</h2>
<p>Per iniziare una vendita è necessaria una sessione di cassa aperta.</p>
<button className="primary-action" onClick={() => onNavigate("Cassa")}>Vai alla cassa</button>
</section>;
  return <section className="new-sale-page">
    <div className="page-title-row">
<div>
<p className="eyebrow">Cassa · {register.name}</p>
<h2>Nuova vendita</h2>
<span>Scansiona un barcode o cerca un articolo.</span>
</div>
<div className="sale-draft-badge">
<ShoppingCart size={18} />{sale ? "Scontrino in corso" : "Scontrino vuoto"}</div>
</div>
    <div className="pos-layout">
<section className="pos-products">
<form className="pos-search" onSubmit={search}>
<Barcode size={21} />
<input ref={inputRef} autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Scansiona barcode o cerca per SKU / nome" />
<button aria-label="Cerca">
<Search size={19} />
</button>
</form>{message && <p className="pos-message">{message}</p>}{matches.length > 1 && <div className="product-matches">{matches.map((variant) => <button key={variant.id} onClick={() => addVariant(variant)}>
<div>
<strong>{variant.product_name}</strong>
<span>{variant.sku} · {variant.color_name || ""} {variant.size_label || ""}</span>
</div>
<b>Seleziona</b>
</button>)}</div>}<div className="pos-hint">
<Barcode size={19} />
<span>Con uno scanner USB il codice viene inserito qui automaticamente: premi Invio per aggiungere l’articolo.</span>
</div>
</section>
      <aside className="receipt-panel">
<div className="receipt-heading">
<div>
<p>Scontrino</p>
<h3>{sale?.number || "Nuova vendita"}</h3>
</div>
<span>{sale?.lines?.length || 0} righe</span>
</div>
<div className="sale-tools"><button type="button" onClick={() => { setCustomerOpen(true); setCustomerQuery(""); setCustomers([]); setCustomerLoading(true); setCustomerError(""); }}>{selectedCustomer?.full_name || sale?.customer_name || "Associa cliente"}</button><button type="button" onClick={openGiftLists}>Carica lista regalo</button></div>
<div className="receipt-lines">{sale?.lines?.length ? sale.lines.map((line) => <div className="receipt-line" key={line.id}>
<div>
<strong>{labels[line.variant] || "Articolo aggiunto"}</strong>
<span>{euro.format(Number(line.net_amount || 0))}</span>
</div>
<div className="quantity-control">
<button onClick={() => changeQuantity(line, -1)} aria-label="Diminuisci quantità">
<Minus size={15} />
</button>
<b>{line.quantity}</b>
<button onClick={() => changeQuantity(line, 1)} aria-label="Aumenta quantità">
<Plus size={15} />
</button>
<button className="remove-sale-line" onClick={() => removeLine(line)} aria-label="Rimuovi articolo">
<Trash2 size={14} />
</button>
</div>
</div>) : <p className="receipt-empty">Lo scontrino è pronto. Aggiungi il primo articolo.</p>}</div>
<div className="receipt-total">
<span>Totale</span>
<strong>{euro.format(Number(sale?.final_total_amount || 0))}</strong>
</div>
<button className="primary-action receipt-pay" disabled={!sale?.lines?.length} onClick={openPayment}>Vai al pagamento</button>
</aside>
</div>
    {reservedPrompt && <div className="payment-layer" role="dialog" aria-modal="true" aria-labelledby="reserved-title">
      <button className="payment-backdrop" aria-label="Annulla" disabled={adding} onClick={() => setReservedPrompt(null)} />
      <section className="payment-dialog sale-selection-dialog reserved-dialog">
        <header><h3 id="reserved-title">Articolo in lista regalo</h3><button type="button" aria-label="Chiudi" disabled={adding} onClick={() => setReservedPrompt(null)}><X size={20} /></button></header>
        <div className="reserved-product"><span>Articolo selezionato</span><strong>{reservedPrompt.variant.product_name || labels[reservedPrompt.variant.id] || reservedPrompt.variant.sku}</strong></div>
        <div className="reserved-lists" role={reservedPrompt.lists.length > 1 ? "radiogroup" : undefined} aria-label="Lista da cui rimuovere l'articolo">
          {reservedPrompt.lists.length > 1 && <p className="reserved-hint">Scegli da quale lista togliere il pezzo.</p>}
          {reservedPrompt.lists.map((entry) => {
            const content = <><span className="reserved-list-info"><strong>{entry.title}</strong><span className="reserved-beneficiary">{entry.beneficiary}</span><span className="reserved-code">{entry.code}</span></span><span className="reserved-count">{entry.quantity} {entry.quantity === 1 ? "pezzo" : "pezzi"}</span></>;
            return reservedPrompt.lists.length === 1
              ? <div key={entry.item} className="reserved-list-card">{content}</div>
              : <label key={entry.item} className={`reserved-list-card reserved-list-option${reservedChoice === entry.item ? " is-selected" : ""}`}><input type="radio" name="release-list" value={entry.item} checked={reservedChoice === entry.item} disabled={adding} onChange={() => setReservedChoice(entry.item)} />{content}</label>;
          })}
        </div>
        <p className="reserved-question">Togliere <strong>1 pezzo</strong> dalla lista e aggiungerlo alla vendita?</p>
        {reservedError && <p className="payment-error" role="alert">{reservedError}</p>}
        <footer><button type="button" className="secondary-action" disabled={adding} onClick={() => { setReservedPrompt(null); inputRef.current?.focus(); }}>Annulla</button>
        <button type="button" className="primary-action" disabled={adding || !reservedChoice} onClick={() => addVariant(reservedPrompt.variant, reservedPrompt)}>{adding ? "Aggiunta…" : "Togli dalla lista e vendi"}</button></footer>
      </section>
    </div>}
    {customerOpen && <div className="payment-layer" role="dialog" aria-modal="true" aria-label="Associa cliente"><button className="payment-backdrop" aria-label="Chiudi" disabled={customerSaving} onClick={() => setCustomerOpen(false)} /><section className="payment-dialog sale-selection-dialog"><header><div><p className="eyebrow">Cliente</p><h3>Associa cliente alla vendita</h3></div><button type="button" aria-label="Chiudi" disabled={customerSaving} onClick={() => setCustomerOpen(false)}><X size={20} /></button></header><form className="customer-search" onSubmit={(event) => { event.preventDefault(); searchCustomers(); }}><input autoFocus aria-label="Cerca cliente per nome, telefono o codice" disabled={customerSaving} value={customerQuery} onChange={(event) => { customerRequest.current += 1; setCustomers([]); setCustomerLoading(true); setCustomerError(""); setCustomerQuery(event.target.value); }} placeholder="Nome, telefono o codice cliente" /><button className="secondary-action" disabled={customerSaving}>Cerca</button></form>{customerError && <p className="selection-empty" role="alert">{customerError}</p>}{customerLoading && <p className="selection-empty" role="status">Ricerca clienti…</p>}{customers.map((customer) => <button type="button" className="selection-row" disabled={customerSaving} key={customer.id} onClick={() => selectCustomer(customer)}><strong>{customer.full_name}</strong><span>{customer.customer_code} · {customer.phone || customer.email || "Nessun contatto"}</span></button>)}{!customerLoading && !customerError && !customers.length && <p className="selection-empty">Nessun cliente trovato.</p>}{!customerLoading && customerMore && <p className="selection-empty">Mostrati i primi 50 risultati. Continua a scrivere per restringere la ricerca.</p>}</section></div>}
    {giftListOpen && <div className="payment-layer" role="dialog" aria-modal="true" aria-label="Carica lista regalo"><button className="payment-backdrop" aria-label="Chiudi" onClick={() => setGiftListOpen(false)} /><section className="payment-dialog sale-selection-dialog"><header><div><p className="eyebrow">Lista regalo</p><h3>{selectedGiftList ? selectedGiftList.title : "Scegli una lista"}</h3></div><button type="button" aria-label="Chiudi" onClick={() => setGiftListOpen(false)}><X size={20} /></button></header>{giftLoading ? <p className="selection-empty">Caricamento in corso…</p> : !selectedGiftList ? giftLists.map((giftList) => <button type="button" className="selection-row" key={giftList.id} onClick={() => selectGiftList(giftList)}><strong>{giftList.title}</strong><span>{giftList.code} · {giftList.beneficiary_first_name} {giftList.beneficiary_last_name}</span></button>) : giftItems.map((item) => { const remaining = Number(item.reserved_quantity || 0) - Number(item.purchased_quantity || 0); return <div className="gift-item-row" key={item.id}><div><strong>{item.variant_data?.product_name || item.variant}</strong><span>{item.variant_data?.sku || ""} · Disponibili dalla lista: {remaining}</span></div><button type="button" className="secondary-action" disabled={remaining < 1} onClick={() => addGiftItem(item)}>Aggiungi</button></div>; })}{!giftLoading && !selectedGiftList && !giftLists.length && <p className="selection-empty">Nessuna lista articoli aperta.</p>}</section></div>}
    {paymentOpen && <div className="payment-layer" role="dialog" aria-modal="true" aria-label="Pagamento vendita">
<button className="payment-backdrop" aria-label="Chiudi" disabled={paying} onClick={() => setPaymentOpen(false)} />
<section className="payment-dialog">
<header>
<div>
<p className="eyebrow">Pagamento</p>
<h3>Concludi la vendita</h3>
</div>
<button type="button" aria-label="Chiudi" disabled={paying} onClick={() => setPaymentOpen(false)}>
<X size={20} />
</button>
</header>
<div className="payment-total">
<span>Totale da pagare</span>
<strong>{euro.format(Number(paymentAmount || 0))}</strong>
</div>
<div className="voucher-apply"><label>Totale arrotondato €<input inputMode="decimal" value={roundedTotal} disabled={paying || Boolean(sale?.payments?.length)} onChange={(event) => setRoundedTotal(event.target.value)} /></label><button type="button" className="secondary-action" disabled={paying || Boolean(sale?.payments?.length)} onClick={applyRounding}>Applica</button></div>
{Boolean(sale?.payments?.length) && <small>Arrotondamento disponibile prima di applicare buoni o registrare pagamenti.</small>}
{Number(sale?.manual_total_adjustment || 0) !== 0 && <p className="payment-change">Arrotondamento applicato: {Number(sale.manual_total_adjustment) > 0 ? "+" : ""}{euro.format(Number(sale.manual_total_adjustment))}</p>}
<label>Metodo di pagamento<select value={paymentMethod} disabled={paying} onChange={(event) => setPaymentMethod(event.target.value)}>
<option value="CASH">Contanti</option>
<option value="CARD">Carta</option>
<option value="OTHER">Altro</option>
</select>
</label>
<label>Importo<input inputMode="decimal" value={paymentAmount} disabled={paying} onChange={(event) => { setPaymentAmount(event.target.value); if (paymentMethod === "CASH") setCashReceived(event.target.value); }} />
</label>{paymentMethod === "CASH" && <label>Contanti ricevuti<input inputMode="decimal" value={cashReceived} disabled={paying} onChange={(event) => setCashReceived(event.target.value)} />
</label>}{paymentMethod !== "CASH" && <label>Riferimento pagamento <small>Facoltativo</small>
<input value={paymentReference} disabled={paying} onChange={(event) => setPaymentReference(event.target.value)} placeholder="Es. numero transazione" />
</label>}{paymentMethod === "CASH" && Number(cashReceived || 0) >= Number(paymentAmount || 0) && <p className="payment-change">Resto: {euro.format(Math.max(0, Number(cashReceived || 0) - Number(paymentAmount || 0)))}</p>}<div className="voucher-apply"><label>Applica buono<input value={voucherCode} disabled={paying} onChange={(event) => setVoucherCode(event.target.value)} placeholder="Codice buono" /></label><button type="button" className="secondary-action" disabled={paying} onClick={applyVoucher}>Applica</button></div>{voucherMessage && <p className="voucher-message">{voucherMessage}</p>}{paymentError && <p className="payment-error" role="alert">{paymentError}</p>}<footer>
<button type="button" className="secondary-action" disabled={paying} onClick={() => setPaymentOpen(false)}>Annulla</button>
<button type="button" className="primary-action" disabled={paying} onClick={completePayment}>{paying ? "Registrazione..." : "Conferma pagamento"}</button>
</footer>
</section>
</div>}
  </section>;
}
