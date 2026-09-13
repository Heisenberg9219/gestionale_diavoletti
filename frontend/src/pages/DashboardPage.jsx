import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  Bell,
  ChevronRight,
  CircleDollarSign,
  ClipboardList,
  CreditCard,
  Menu,
  PackageCheck,
  Plus,
  ScanLine,
  ShoppingBag,
  UsersRound,
} from "lucide-react";
import Sidebar from "../components/Sidebar";
import MetricCard from "../components/MetricCard";
import { request } from "../api";
import SalesPage from "./SalesPage";
import CashPage from "./CashPage";
import NewSalePage from "./NewSalePage";
import ReturnsPage from "./ReturnsPage";
import CatalogPage from "./CatalogPage";
import InventoryPage from "./InventoryPage";
import CountsPage from "./CountsPage";
import ReordersPage from "./ReordersPage";
import CustomersPage from "./CustomersPage";
import LoyaltyPage from "./LoyaltyPage";
import VoucherPage from "./VoucherPage";
import GiftListsPage from "./GiftListsPage";
import SuppliersPage from "./SuppliersPage";
import PurchaseOrdersPage from "./PurchaseOrdersPage";
import PromotionsPage from "./PromotionsPage";
import ExpensesPage from "./ExpensesPage";
import DocumentsOcrPage from "./DocumentsOcrPage";
import NotificationsPage from "./NotificationsPage";
import IntegrationsPage from "./IntegrationsPage";
import ReportsPage from "./ReportsPage";
import UsersRolesPage from "./UsersRolesPage";
import logo from "../assets/diavoletti-logo-transparent.png";
import "../dashboard.css";
import "../dashboard-overrides.css";

const emptyOverview = {
  metrics: { revenue: "0.00", sales_count: 0, units_sold: 0, new_customers: 0 },
  recent_sales: [],
  stock: { out_of_stock_balances: 0, units_on_hand: 0 },
};

const euro = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
const notificationTarget = {
  "expenses.Expense": "Spese",
  "reorders.ReorderItem": "Riordini",
  "vouchers.Voucher": "Buoni",
  "giftlists.GiftList": "Liste regalo",
  "inventory.StockBalance": "Magazzino",
};
const asList = (data) => data?.results || data || [];

export default function DashboardPage({ user, onLogout }) {
  const isClerk = user?.roles?.includes("Commesso") && !user?.is_superuser;
  const allowedPages = isClerk ? (user?.page_permissions || []) : null;
  const [active, setActive] = useState(isClerk ? (allowedPages[0] || "") : "Panoramica");
  const [mobileMenu, setMobileMenu] = useState(false);
  const [returnSale, setReturnSale] = useState(null);
  const [overview, setOverview] = useState(emptyOverview);
  const [loading, setLoading] = useState(true);
  const [bellOpen, setBellOpen] = useState(false);
  const [bellItems, setBellItems] = useState([]);
  const firstName = user?.first_name || user?.email?.split("@")[0] || "Mario";

  useEffect(() => {
    if (isClerk && !allowedPages.includes(active)) setActive(allowedPages[0] || "");
  }, [active, allowedPages, isClerk]);

  useEffect(() => {
    if (isClerk) {
      setLoading(false);
      return undefined;
    }
    request("/reporting/overview/")
      .then(setOverview)
      .catch(() => setOverview(emptyOverview))
      .finally(() => setLoading(false));
    return undefined;
  }, [isClerk]);

  useEffect(() => {
    let disposed = false;
    const loadBellItems = async () => {
      try {
        const [notifications, deliveries] = await Promise.all([
          request("/notifications/notifications/"),
          request("/notifications/deliveries/"),
        ]);
        if (disposed) return;
        const deliveryByNotification = new Map(asList(deliveries).map((delivery) => [delivery.notification, delivery]));
        setBellItems(asList(notifications)
          .map((notification) => ({ notification, delivery: deliveryByNotification.get(notification.id) }))
          .filter(({ notification, delivery }) => notification.status === "ACTIVE" && delivery && !delivery.archived_at));
      } catch {
        if (!disposed) setBellItems([]);
      }
    };
    loadBellItems();
    const interval = window.setInterval(loadBellItems, 30000);
    return () => { disposed = true; window.clearInterval(interval); };
  }, []);

  const unreadBellItems = bellItems.filter(({ delivery }) => !delivery.read_at);
  const openNotification = async ({ notification, delivery }) => {
    if (!delivery.read_at) {
      try {
        await request(`/notifications/deliveries/${delivery.id}/mark-read/`, { method: "POST", body: JSON.stringify({}) });
        setBellItems((items) => items.map((item) => item.delivery.id === delivery.id ? { ...item, delivery: { ...item.delivery, read_at: new Date().toISOString() } } : item));
      } catch { /* La navigazione resta disponibile anche se il segno di lettura fallisce. */ }
    }
    setBellOpen(false);
    setActive(notificationTarget[notification.source_type] || "Notifiche");
  };

  return (
    <main className="dashboard-shell">
      {mobileMenu && <button className="mobile-sidebar-backdrop" type="button" aria-label="Chiudi menu" onClick={() => setMobileMenu(false)} />}
      <Sidebar active={active} onNavigate={setActive} onLogout={onLogout} mobileOpen={mobileMenu} onClose={() => setMobileMenu(false)} allowedPages={allowedPages} />
      <style>{`
        .mobile-menu-button, .mobile-sidebar-close, .mobile-sidebar-backdrop { display: none; }
        .dashboard-main > :not(.dashboard-watermark):not(.mobile-dashboard-nav):not(style) { position: relative; z-index: 1; }
        .loyalty-form > button:nth-last-child(2), .loyalty-form > button:last-child { width: 135px; min-width: 135px; padding: 0 14px; }
        .loyalty-form > button:last-child { grid-column: 3; justify-self: end; }
        .loyalty-form > button:nth-last-child(2) { grid-column: 4; justify-self: start; }
        .table-selection-actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; color: #716a70; font-size: 12px; font-weight: 800; }
        .table-selection-actions button { display: flex; align-items: center; gap: 7px; height: 38px; border: 1px solid #e2dddf; border-radius: 8px; padding: 0 12px; background: #fff; color: #403a3f; font: inherit; cursor: pointer; }
        .table-selection-actions .delete-selected { border: 0; background: #ed001b; color: #fff; }
        .customer-heading, .customer-row { grid-template-columns: 34px minmax(0,1.3fr) minmax(180px,.8fr) 160px 92px; }
        .vouchers-heading, .voucher-row { grid-template-columns: 34px minmax(180px,1.25fr) minmax(130px,.9fr) 130px 110px 100px; }
        .table-row-check { display: grid !important; place-items: center; }
        .table-row-check input { width: 17px; height: 17px; accent-color: #178c82; cursor: pointer; }
        .dashboard-header { position: relative; z-index: 40; }
        .notification-menu { position: relative; z-index: 45; }
        .notification-menu > .icon-button i { display: none; }
        .notification-menu > .icon-button.has-unread i { display: block; }
        .header-notifications { position: absolute; top: calc(100% + 10px); right: 0; z-index: 50; width: min(340px, calc(100vw - 32px)); overflow: hidden; border: 1px solid #e7e1e3; border-radius: 8px; background: #fff; box-shadow: 0 16px 40px rgba(24,21,26,.18); }
        .header-notifications-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 15px 10px; border-bottom: 1px solid #f0ebed; }
        .header-notifications-head strong { font-size: 14px; }
        .header-notifications-head span { color: #8a8388; font-size: 11px; font-weight: 800; }
        .header-notification-item { display: grid; width: 100%; gap: 4px; padding: 13px 15px; border: 0; border-bottom: 1px solid #f2edef; background: #fff; color: #282329; text-align: left; font: inherit; cursor: pointer; }
        .header-notification-item:hover { background: #fff7f8; }
        .header-notification-item.unread strong::before { content: ""; display: inline-block; width: 7px; height: 7px; margin: 0 7px 1px 0; border-radius: 50%; background: #ed001b; }
        .header-notification-item strong { font-size: 12px; }
        .header-notification-item span { overflow: hidden; color: #777076; font-size: 11px; line-height: 1.35; text-overflow: ellipsis; white-space: nowrap; }
        .header-notifications-empty { display: block; padding: 24px 15px; color: #817b80; font-size: 12px; text-align: center; }
        .header-notifications-footer { display: flex; width: 100%; justify-content: center; padding: 11px; border: 0; background: #fff; color: #cc001b; font: inherit; font-size: 12px; font-weight: 900; cursor: pointer; }
        .customer-row.selected, .voucher-row.selected { background: #edf8f7; }
        .customer-row > div:nth-child(2) { display: grid; gap: 4px; }
        .voucher-filters { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
        .status-tabs { display: flex; align-items: center; gap: 5px; }
        .status-tabs button { height: 34px; border: 0; border-radius: 7px; padding: 0 10px; background: transparent; color: #777176; font-size: 11px; font-weight: 800; cursor: pointer; }
        .status-tabs button.active { background: #18151a; color: #fff; }
        @media (max-width: 1000px) { .loyalty-form > button:last-child { grid-column: 1; width: 100%; min-width: 0; justify-self: stretch; } .loyalty-form > button:nth-last-child(2) { grid-column: 2; width: 100%; min-width: 0; justify-self: stretch; } }
        @media (max-width: 640px) { .loyalty-form { grid-template-columns: 1fr 1fr; } .loyalty-form > label { grid-column: 1 / -1; } }
        @media (max-width: 760px) {
          .dashboard-main { width: 100%; max-width: 100%; box-sizing: border-box; padding: 24px 16px 108px; }
          .dashboard-header { position: relative; align-items: flex-start; gap: 12px; min-height: 60px; }
          .dashboard-header > div:first-child { padding-left: 56px; }
          .header-actions { gap: 8px; flex-shrink: 0; }
          .dashboard-grid { grid-template-columns: minmax(0, 1fr); width: 100%; }
          .dashboard-panel { min-width: 0; box-sizing: border-box; }
          .mobile-menu-button { display: grid; position: absolute; top: 0; left: 0; place-items: center; width: 42px; height: 42px; padding: 0; border: 1px solid #e4dde0; border-radius: 10px; background: #fff; color: #18151a; }
          .mobile-sidebar-backdrop { display: block; position: fixed; inset: 0; z-index: 90; border: 0; background: rgba(24, 21, 26, .42); }
          .dashboard-sidebar.mobile-open { display: flex !important; position: fixed !important; inset: 0 auto 0 0 !important; z-index: 100 !important; width: min(290px, 86vw) !important; box-sizing: border-box; box-shadow: 18px 0 45px rgba(24, 21, 26, .25); }
          .dashboard-sidebar.mobile-open .sidebar-footer { margin-top: auto; }
          .mobile-sidebar-close { display: grid; place-items: center; width: 34px; height: 34px; margin-left: auto; padding: 0; border: 0; border-radius: 8px; background: transparent; color: currentColor; }
          .dashboard-watermark { width: 170px !important; right: 10px !important; bottom: 82px !important; opacity: .1 !important; }
          .header-notifications { top: calc(100% + 8px); right: 0; width: min(340px, calc(100vw - 32px)); }
          .loyalty-form > button:nth-last-child(2), .loyalty-form > button:last-child { grid-column: auto; width: auto; min-width: 0; justify-self: stretch; }
          .table-selection-actions { justify-content: flex-start; flex-wrap: wrap; }
          .voucher-filters { align-items: stretch; flex-direction: column; }
          .status-tabs { overflow-x: auto; padding-bottom: 2px; }
          .customer-row, .voucher-row { grid-template-columns: 28px 1fr auto; }
          .customer-row > span, .customer-row > b, .voucher-row > span { display: none; }
          .customer-row .table-row-check, .voucher-row .table-row-check { grid-column: 1; grid-row: 1; }
          .customer-row > div:nth-child(2), .voucher-row > div:nth-child(2) { grid-column: 2; grid-row: 1; }
          .customer-actions { grid-column: 3; grid-row: 1; }
          .voucher-row > b { grid-column: 3; grid-row: 1; }
          .voucher-status { grid-column: 2; grid-row: 2; }
        }
      `}</style>
      <section className="dashboard-main">
        <img className="dashboard-watermark" src={logo} alt="" aria-hidden="true" style={{ position: "fixed", right: 22, bottom: 18, width: "min(250px, 22vw)", opacity: 0.11, pointerEvents: "none", zIndex: 0 }} />
        <header className="dashboard-header">
          <div>
            <p>{new Intl.DateTimeFormat("it-IT", { weekday: "long", day: "numeric", month: "long" }).format(new Date())}</p>
            <h1>Buongiorno, {firstName}.</h1>
          </div>
          <div className="header-actions">
            <button className="mobile-menu-button" type="button" aria-label="Apri menu" onClick={() => setMobileMenu(true)}><Menu size={22} /></button>
            <div className="notification-menu">
              <button className={`icon-button ${unreadBellItems.length ? "has-unread" : ""}`} type="button" aria-label="Notifiche" aria-expanded={bellOpen} onClick={() => setBellOpen((open) => !open)}><Bell size={20} /><i /></button>
              {bellOpen && <div className="header-notifications" role="dialog" aria-label="Notifiche recenti"><div className="header-notifications-head"><strong>Notifiche</strong><span>{unreadBellItems.length ? `${unreadBellItems.length} non lette` : "Tutto letto"}</span></div>{bellItems.length ? bellItems.slice(0, 5).map((item) => <button className={`header-notification-item ${item.delivery.read_at ? "" : "unread"}`} key={item.notification.id} type="button" onClick={() => openNotification(item)}><strong>{item.notification.title}</strong><span>{item.notification.message}</span></button>) : <span className="header-notifications-empty">Nessun nuovo evento.</span>}<button className="header-notifications-footer" type="button" onClick={() => { setBellOpen(false); setActive("Notifiche"); }}>Visualizza tutte</button></div>}
            </div>
            <button className="profile-button"><span>{firstName.slice(0, 1).toUpperCase()}</span><strong>{firstName}</strong></button>
          </div>
        </header>

        {isClerk && !active ? <section className="empty-product-state"><Bell size={28} /><strong>Nessuna pagina abilitata</strong><span>Il titolare deve assegnarti almeno un permesso dalla pagina Utenti e ruoli.</span></section> : active === "Storico vendite" ? <SalesPage onStartReturn={(sale) => { setReturnSale(sale); setActive("Resi"); }} /> : active === "Cassa" ? <CashPage onNavigate={setActive} /> : active === "Nuova vendita" ? <NewSalePage onNavigate={setActive} /> : active === "Resi" ? <ReturnsPage onNavigate={setActive} initialSale={returnSale} onClearInitialSale={() => setReturnSale(null)} /> : active === "Catalogo" ? <CatalogPage /> : active === "Magazzino" ? <InventoryPage /> : active === "Inventari" ? <CountsPage /> : active === "Riordini" ? <ReordersPage /> : active === "Clienti" ? <CustomersPage /> : active === "Fedeltà" ? <LoyaltyPage /> : active === "Buoni" ? <VoucherPage /> : active === "Liste regalo" ? <GiftListsPage /> : active === "Fornitori" ? <SuppliersPage /> : active === "Ordini acquisto" ? <PurchaseOrdersPage /> : active === "Promozioni" ? <PromotionsPage /> : active === "Spese" ? <ExpensesPage /> : active === "Documenti e OCR" ? <DocumentsOcrPage /> : active === "Notifiche" ? <NotificationsPage onNavigate={setActive} /> : active === "Integrazioni" ? <IntegrationsPage /> : active === "Report" ? <ReportsPage /> : active === "Utenti e ruoli" ? <UsersRolesPage currentUser={user} /> : <>
        <section className="dashboard-overview">
          <div className="overview-copy">
            <p className="eyebrow">Situazione di oggi</p>
            <h2>Tutto pronto per una buona giornata.</h2>
            <span>{loading ? "Aggiornamento dati in corso..." : "Dati aggiornati in tempo reale dal gestionale."}</span>
          </div>
          <div className="quick-actions">
            <button className="primary-action" type="button" onClick={() => setActive("Nuova vendita")}><Plus size={18} /> Nuova vendita</button>
            <button className="secondary-action" type="button" onClick={() => setActive("Catalogo")}><ScanLine size={18} /> Cerca articolo</button>
          </div>
        </section>

        <section className="metrics-grid" aria-label="Riepilogo giornata">
          <MetricCard label="Incasso di oggi" value={euro.format(Number(overview.metrics.revenue))} change="Vendite confermate oggi" tone="red" icon={CircleDollarSign} />
          <MetricCard label="Vendite concluse" value={overview.metrics.sales_count} change="Scontrini confermati oggi" icon={ShoppingBag} />
          <MetricCard label="Pezzi venduti" value={overview.metrics.units_sold} change="Articoli venduti oggi" icon={PackageCheck} />
          <MetricCard label="Nuovi clienti" value={overview.metrics.new_customers} change="Anagrafiche create oggi" icon={UsersRound} />
        </section>

        <section className="dashboard-grid">
          <article className="dashboard-panel recent-sales">
            <div className="panel-heading"><div><p>In tempo reale</p><h2>Ultime vendite</h2></div><button type="button" onClick={() => setActive("Storico vendite")}>Vedi tutte <ChevronRight size={17} /></button></div>
            <div className="sales-table">
              {overview.recent_sales.length ? overview.recent_sales.map((sale) => <div className="sale-row" key={sale.id}><div><strong>{sale.customer_name}</strong><span>{sale.number} · {new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" }).format(new Date(sale.confirmed_at))}</span></div><span className="sale-status">Completata</span><strong>{euro.format(Number(sale.total_amount))}</strong></div>) : <p className="empty-sales">Nessuna vendita confermata oggi.</p>}
            </div>
          </article>
          <article className="dashboard-panel stock-panel">
            <div className="panel-heading"><div><p>Attenzione</p><h2>Scorte esaurite</h2></div><button type="button" aria-label="Apri magazzino" onClick={() => setActive("Magazzino")}><ArrowUpRight size={18} /></button></div>
            <div className="stock-number">{overview.stock.out_of_stock_balances} <span>giacenze</span></div>
            <p>sono attualmente a zero nelle sedi di magazzino.</p>
            <button className="stock-action" type="button" onClick={() => setActive("Riordini")}><ClipboardList size={17} /> Apri lista riordino</button>
          </article>
        </section>

        <section className="mobile-dashboard-nav" aria-label="Azioni rapide">
          <button className="active" type="button" onClick={() => setActive("Nuova vendita")}><ShoppingBag size={20} />Vendite</button>
          <button type="button" onClick={() => setActive("Catalogo")}><ScanLine size={20} />Cerca</button>
          <button type="button" onClick={() => setActive("Cassa")}><CreditCard size={20} />Cassa</button>
        </section>
        </>}
      </section>
    </main>
  );
}
