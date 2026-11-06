import { useEffect, useState } from "react";
import { Baby, Pencil, Ticket, X } from "lucide-react";
import { request } from "../api";

// Scheda cliente: figli con taglia indicativa, punti, buoni attivi e ultimi acquisti.

const euro = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
const shortDate = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short", year: "numeric" });
const list = (data) => data?.results || data || [];

// Taglia europea bambino indicativa (altezza media in cm) in base all'età.
const SIZE_BY_MONTHS = [
  [3, "56–62"],
  [6, "68"],
  [9, "74"],
  [12, "80"],
  [18, "86"],
  [24, "92"],
  [36, "98"],
  [48, "104"],
  [60, "110"],
  [72, "116"],
  [84, "122"],
  [96, "128"],
  [108, "134"],
  [120, "140"],
  [132, "146"],
  [144, "152"],
  [156, "158"],
  [168, "164"],
  [204, "170"],
];
function monthsSince(value) {
  if (!value) return null;
  const birth = new Date(`${value}T00:00:00`);
  const now = new Date();
  let months = (now.getFullYear() - birth.getFullYear()) * 12 + now.getMonth() - birth.getMonth();
  if (now.getDate() < birth.getDate()) months -= 1;
  return months;
}
function childInfo(child) {
  if (!child.birth_date && child.expected_birth_date)
    return `In arrivo il ${shortDate.format(new Date(`${child.expected_birth_date}T00:00:00`))}`;
  const months = monthsSince(child.birth_date);
  if (months === null || months < 0) return "Età non indicata";
  const age = months < 24 ? `${months} ${months === 1 ? "mese" : "mesi"}` : `${Math.floor(months / 12)} anni`;
  const size = SIZE_BY_MONTHS.find(([limit]) => months < limit)?.[1];
  return size ? `${age} · taglia indicativa ${size}` : age;
}

export default function CustomerCard({ customer, onClose, onEdit }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    let alive = true;
    setData(null);
    const id = customer.id;
    Promise.all([
      request(`/customers/children/?customer=${id}&page_size=50`)
        .then(list)
        .catch(() => []),
      request(`/loyalty/point-movements/balance/?customer=${id}`)
        .then((payload) => payload.points)
        .catch(() => null),
      request(`/vouchers/vouchers/?customer=${id}&status=ACTIVE&page_size=20`)
        .then(list)
        .catch(() => null),
      request(`/sales/sales/?customer=${id}&status=CONFIRMED&ordering=-opened_at&page_size=8`).catch(
        () => null,
      ),
    ]).then(([children, points, vouchers, sales]) => {
      if (!alive) return;
      setData({
        children: children.filter((child) => child.is_active !== false),
        points,
        vouchers,
        sales: sales ? list(sales) : null,
        salesCount: sales?.count ?? (sales ? list(sales).length : 0),
      });
    });
    return () => {
      alive = false;
    };
  }, [customer.id]);

  const voucherTotal = (data?.vouchers || []).reduce(
    (sum, voucher) => sum + Number(voucher.current_balance || 0),
    0,
  );

  return (
    <aside className="sale-detail customer-card" aria-label={`Scheda di ${customer.full_name}`}>
      <header>
        <div>
          <p className="eyebrow">Scheda cliente</p>
          <h3>{customer.full_name}</h3>
          <span>{customer.customer_code}</span>
        </div>
        <span className="customer-card-actions">
          <button type="button" className="sale-detail-close" title="Modifica cliente" onClick={onEdit}>
            <Pencil size={16} />
          </button>
          <button type="button" className="sale-detail-close" aria-label="Chiudi" onClick={onClose}>
            <X size={18} />
          </button>
        </span>
      </header>
      <dl className="sale-detail-facts">
        <div>
          <dt>Telefono</dt>
          <dd>{customer.phone || "—"}</dd>
        </div>
        <div>
          <dt>Email</dt>
          <dd>{customer.email || "—"}</dd>
        </div>
        <div>
          <dt>Città</dt>
          <dd>{customer.city || "—"}</dd>
        </div>
        <div>
          <dt>Data di nascita</dt>
          <dd>
            {customer.birth_date
              ? shortDate.format(new Date(`${customer.birth_date}T00:00:00`))
              : "Non indicata"}
          </dd>
        </div>
      </dl>
      {!data ? (
        <p className="empty-note">Caricamento scheda…</p>
      ) : (
        <>
          <div className="customer-card-kpis">
            <div>
              <span>Acquisti</span>
              <b>{data.sales ? data.salesCount : "—"}</b>
            </div>
            <div>
              <span>Punti fedeltà</span>
              <b>{data.points ?? "—"}</b>
            </div>
            <div>
              <span>Credito nei buoni</span>
              <b>{data.vouchers ? euro.format(voucherTotal) : "—"}</b>
            </div>
          </div>
          {data.children.length > 0 && (
            <section className="customer-card-section">
              <h4>
                <Baby size={15} /> Bambini
              </h4>
              {data.children.map((child) => (
                <div className="customer-card-line" key={child.id}>
                  <b>{child.first_name}</b>
                  <span>{childInfo(child)}</span>
                </div>
              ))}
            </section>
          )}
          {data.vouchers && data.vouchers.length > 0 && (
            <section className="customer-card-section">
              <h4>
                <Ticket size={15} /> Buoni attivi
              </h4>
              {data.vouchers.map((voucher) => (
                <div className="customer-card-line" key={voucher.id}>
                  <b className="mono">{voucher.code}</b>
                  <span>
                    {euro.format(Number(voucher.current_balance || 0))}
                    {voucher.expires_at
                      ? ` · scade il ${shortDate.format(new Date(voucher.expires_at))}`
                      : ""}
                  </span>
                </div>
              ))}
            </section>
          )}
          <section className="customer-card-section">
            <h4>Ultimi acquisti</h4>
            {!data.sales ? (
              <p className="empty-note">Storico acquisti non disponibile.</p>
            ) : !data.sales.length ? (
              <p className="empty-note">Nessun acquisto registrato a nome di questo cliente.</p>
            ) : (
              data.sales.map((sale) => (
                <div className="customer-card-line" key={sale.id}>
                  <b>{sale.number}</b>
                  <span>
                    {shortDate.format(new Date(sale.confirmed_at || sale.opened_at))} ·{" "}
                    {(sale.lines || [])
                      .map((line) =>
                        [line.product_name_snapshot, line.size_snapshot].filter(Boolean).join(" "),
                      )
                      .slice(0, 2)
                      .join(", ")}
                    {(sale.lines || []).length > 2 ? "…" : ""}
                  </span>
                  <span className="money">{euro.format(Number(sale.final_total_amount || 0))}</span>
                </div>
              ))
            )}
          </section>
        </>
      )}
    </aside>
  );
}
