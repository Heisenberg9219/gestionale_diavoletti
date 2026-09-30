import { useEffect, useState } from "react";
import { request } from "../api";
import "./VoucherCustomerPicker.css";

const birthday = (value) => value ? new Date(`${value}T00:00:00`).toLocaleDateString("it-IT") : "Data di nascita non indicata";

export default function VoucherCustomerPicker({ customer, onSelect, disabled }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  useEffect(() => {
    if (customer || !query.trim()) return;
    let active = true;
    const timer = setTimeout(async () => {
      try {
        const data = await request(`/customers/customers/?search=${encodeURIComponent(query.trim())}&ordering=last_name,first_name&page_size=30`);
        if (active) { setResults(data.results || data); setHasMore(Boolean(data.next)); }
      } catch (exception) { if (active) setError(exception.message); }
      finally { if (active) setLoading(false); }
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [query, customer]);
  return <div className="voucher-customer-picker">
    {customer ? <div className="voucher-selected-customer"><div><strong>{customer.first_name} {customer.last_name}</strong><span>{birthday(customer.birth_date)}</span></div><button type="button" disabled={disabled} onClick={() => { setQuery(""); setResults([]); setError(""); setLoading(false); onSelect(null); }}>Cambia cliente</button></div> : <>
      <label>Cerca cliente per cognome<input disabled={disabled} autoComplete="off" value={query} placeholder="Inizia a scrivere il cognome" onChange={(event) => { setQuery(event.target.value); setResults([]); setError(""); setHasMore(false); setLoading(Boolean(event.target.value.trim())); }} /></label>
      {query.trim() && <div className="voucher-customer-results" aria-live="polite">
        {loading ? <p>Ricerca…</p> : error ? <p role="alert">{error}</p> : results.length ? <><ul>{results.map((entry) => <li key={entry.id}><button type="button" disabled={disabled} onClick={() => onSelect(entry)}><strong>{entry.first_name} {entry.last_name}</strong><span>{birthday(entry.birth_date)}</span></button></li>)}</ul>{hasMore && <p>Scrivi altre lettere per restringere la ricerca.</p>}</> : <p>Nessun cliente trovato.</p>}
      </div>}
    </>}
  </div>;
}
