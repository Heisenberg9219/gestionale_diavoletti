import { useState } from "react";
import { BarChart3, Bell, Boxes, ChevronDown, ClipboardCheck, ContactRound, CreditCard, FileScan, Gift, HandCoins, LayoutDashboard, LogOut, PackageSearch, Percent, ReceiptText, RefreshCcw, ShoppingBag, ShoppingCart, SlidersHorizontal, Truck, UserRoundCog, UsersRound, WalletCards, X } from "lucide-react";
import logo from "../assets/diavoletti-logo-transparent.png";

const navigationGroups = [
  { label: "Operatività", icon: LayoutDashboard, items: [{ label: "Panoramica", icon: LayoutDashboard }, { label: "Storico vendite", icon: ShoppingBag }, { label: "Nuova vendita", icon: ShoppingCart }, { label: "Cassa", icon: CreditCard }, { label: "Resi", icon: RefreshCcw }] },
  { label: "Prodotti", icon: Boxes, items: [{ label: "Catalogo", icon: PackageSearch }, { label: "Magazzino", icon: Boxes }, { label: "Inventari", icon: ClipboardCheck }, { label: "Riordini", icon: ShoppingCart }] },
  { label: "Clienti", icon: UsersRound, items: [{ label: "Clienti", icon: UsersRound }, { label: "Fedeltà", icon: HandCoins }, { label: "Buoni", icon: WalletCards }, { label: "Liste regalo", icon: Gift }] },
  { label: "Acquisti", icon: Truck, items: [{ label: "Fornitori", icon: Truck }, { label: "Ordini acquisto", icon: ReceiptText }] },
  { label: "Marketing", icon: Percent, items: [{ label: "Promozioni", icon: Percent }] },
  { label: "Gestione", icon: FileScan, items: [{ label: "Spese", icon: ReceiptText }, { label: "Documenti e OCR", icon: FileScan }, { label: "Notifiche", icon: Bell }] },
  { label: "Controllo", icon: BarChart3, items: [{ label: "Integrazioni", icon: SlidersHorizontal }, { label: "Report", icon: BarChart3 }, { label: "Utenti e ruoli", icon: UserRoundCog }] },
];

export default function Sidebar({ active = "Panoramica", onNavigate, onLogout, mobileOpen = false, onClose, allowedPages = null }) {
  const [openGroup, setOpenGroup] = useState("Operatività");
  return <aside className={`dashboard-sidebar${mobileOpen ? " mobile-open" : ""}`}>
    <div className="sidebar-brand"><span className="sidebar-face" style={{ width: 32, height: 42, display: "block", flex: "0 0 auto", borderRadius: 0, backgroundColor: "transparent", backgroundImage: `url(${logo})`, backgroundRepeat: "no-repeat", backgroundSize: "102px auto", backgroundPosition: "right top", filter: "drop-shadow(0 2px 3px #0008)" }} aria-label="I Diavoletti" /><strong>I Diavoletti</strong><button className="mobile-sidebar-close" type="button" aria-label="Chiudi menu" onClick={onClose}><X size={19} /></button></div>
    <nav aria-label="Navigazione principale">
      {navigationGroups.map(({ label, icon: GroupIcon, items }) => {
        const visibleItems = allowedPages === null ? items : items.filter((item) => allowedPages.includes(item.label));
        if (!visibleItems.length) return null;
        const isOpen = openGroup === label;
        return <section className={isOpen ? "nav-group open" : "nav-group"} key={label}>
          <button className="nav-group-trigger" onClick={() => setOpenGroup(isOpen ? null : label)} aria-expanded={isOpen}>
            <span><GroupIcon size={19} />{label}</span><ChevronDown size={17} />
          </button>
          {isOpen && <div className="nav-submenu">
            {visibleItems.map(({ label: itemLabel, icon: Icon }) => <button className={itemLabel === active ? "nav-item active" : "nav-item"} key={itemLabel} onClick={() => { setOpenGroup(label); onNavigate(itemLabel); onClose?.(); }}><Icon size={17} /><span>{itemLabel}</span></button>)}
          </div>}
        </section>;
      })}
    </nav>
    <div className="sidebar-footer"><button className="logout-button" onClick={() => { onClose?.(); onLogout(); }}><LogOut size={18} /> Esci</button><p className="sidebar-powered">Powered by <strong>Mario Gianfagna</strong></p></div>
  </aside>;
}
