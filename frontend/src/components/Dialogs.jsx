import { useEffect, useRef, useState } from "react";

// Finestre di dialogo del gestionale al posto di window.prompt/window.confirm.
// Le pagine chiamano `await askText(...)` o `await askConfirm(...)` come
// facevano con le funzioni del browser; <DialogHost /> (montato una sola volta
// in App) mostra la finestra e restituisce la risposta.

let showDialog = null;

function openDialog(options) {
  return new Promise((resolve) => {
    if (!showDialog) {
      // Ripiego se l'host non è montato: comportamento di prima.
      resolve(
        options.kind === "text"
          ? window.prompt(options.message, options.defaultValue)
          : window.confirm(options.message),
      );
      return;
    }
    showDialog({ ...options, resolve });
  });
}

// Restituisce il testo inserito, oppure null se l'utente annulla.
export function askText(message, defaultValue = "") {
  return openDialog({
    kind: "text",
    message,
    defaultValue: defaultValue == null ? "" : String(defaultValue),
  });
}

// Restituisce true se l'utente conferma, false altrimenti.
export function askConfirm(message, { confirmLabel = "Conferma" } = {}) {
  return openDialog({ kind: "confirm", message, confirmLabel });
}

export function DialogHost() {
  const [current, setCurrent] = useState(null);
  const [value, setValue] = useState("");
  const currentRef = useRef(null);

  useEffect(() => {
    showDialog = (options) => {
      // Una nuova richiesta chiude come "annullata" quella eventualmente aperta.
      const previous = currentRef.current;
      if (previous) previous.resolve(previous.kind === "text" ? null : false);
      currentRef.current = options;
      setValue(options.defaultValue ?? "");
      setCurrent(options);
    };
    return () => {
      showDialog = null;
    };
  }, []);

  if (!current) return null;

  function close(result) {
    current.resolve(result);
    currentRef.current = null;
    setCurrent(null);
  }
  const cancel = () => close(current.kind === "text" ? null : false);
  function submit(event) {
    event.preventDefault();
    close(current.kind === "text" ? value : true);
  }

  return (
    <div
      className="app-dialog-layer"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) cancel();
      }}
    >
      <form
        className="app-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={current.message}
        onSubmit={submit}
        onKeyDown={(event) => {
          if (event.key === "Escape") cancel();
        }}
      >
        <p>{current.message}</p>
        {current.kind === "text" && (
          <input
            autoFocus
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onFocus={(event) => event.target.select()}
          />
        )}
        <div className="app-dialog-actions">
          <button type="button" className="secondary-action" onClick={cancel}>
            Annulla
          </button>
          <button type="submit" className="primary-action" autoFocus={current.kind === "confirm"}>
            {current.kind === "text" ? "OK" : current.confirmLabel}
          </button>
        </div>
      </form>
    </div>
  );
}
