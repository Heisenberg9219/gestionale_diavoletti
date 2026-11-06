import { useEffect, useState } from "react";

// Messaggi brevi in basso a destra ("Salvato", "Vendita registrata").
// Le pagine chiamano notify("testo") oppure notify("testo", { tone: "error" });
// con { action: { label, run } } il messaggio offre un pulsante, ad esempio "Annulla".

let push = null;
let nextId = 1;

export function notify(message, { tone = "success", action = null, duration = 4200 } = {}) {
  if (!message) return;
  if (!push) return;
  push({ id: nextId++, message, tone, action, duration });
}

export function ToastHost() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    push = (item) => {
      setItems((current) => [...current.slice(-3), item]);
      window.setTimeout(() => setItems((current) => current.filter((x) => x.id !== item.id)), item.duration);
    };
    return () => {
      push = null;
    };
  }, []);

  if (!items.length) return null;
  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {items.map((item) => (
        <div className={`toast ${item.tone}`} key={item.id}>
          <span>{item.message}</span>
          {item.action && (
            <button
              type="button"
              onClick={() => {
                item.action.run();
                setItems((current) => current.filter((x) => x.id !== item.id));
              }}
            >
              {item.action.label}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
