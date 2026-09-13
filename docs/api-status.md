# Verifica API - 2026-09-02

Base: `/api/v1/`. Le modifiche sono locali, non committate o pubblicate.
Presenza di una rotta non significa copertura completa dei suoi casi d'uso.

## Implementato

| Modulo | Risorse e azioni presenti |
| --- | --- |
| auth | Login, refresh via cookie, logout, utente corrente, controllo stato account |
| core | Sedi, impostazioni negozio, aliquote |
| catalog | Marchi, categorie, stagioni, colori, scale/taglie, prodotti, varianti, barcode |
| suppliers | Fornitori e associazioni variante-fornitore |
| pricing | Prezzi di vendita, creazione nuova validita', ricerca prezzo corrente |
| customers | Clienti, figli, finalita' e registrazione consensi |
| inventory | Giacenze, costi, movimenti, rettifiche, trasferimenti, conteggi fisici |
| sales | Casse, apertura/chiusura sessioni, vendite, righe, pagamenti, conferma, prezzo manuale e totale manuale |
| loyalty | Regole, attivazioni, saldo, rettifiche manuali, definizioni, emissione e applicazione/rimozione premi in vendita |
| purchasing | Ordini/righe, invio, ricevimenti/righe e conferma, fatture/righe e conferma |
| promotions | Campagne, attivazioni, regole, offerte, inclusioni/esclusioni, scelta/applicazione/rimozione, andamento |
| vouchers | Emissione, saldo, riscatto, modifica scadenza, autorizzazione scaduto, annullamento |
| gift-lists | Liste, articoli, contributi, chiusura con buono, autorizzazione stock, registrazione acquisto |
| expenses | Categorie, spese, allegati, apertura, pagamenti, annullamento |
| documents | Tipologie, documenti, allegati, finalizzazione e annullamento |
| notifications | Notifiche personali, lettura, archiviazione, risoluzione |
| returns | Bozza reso, righe, conferma, annullamento |
| reorders | Aggiunta, modifica, rimozione, collegamento ordine, completamento, raggruppamento fornitore |
| integrations | Connessioni, mapping, lettura eventi/ordini, accodamento sincronizzazione inventario |
| reporting | Dashboard, widget, metriche vendite/reso/magazzino, confronti, snapshot, esportazioni CSV/XLSX tracciate |

## Correzioni della ripresa

- Risposte composite per riscatto buono e chiusura lista regalo.
- Serializzazione riordini raggruppati e modifica scadenza buono.
- Rettifiche punti e deroghe buoni riservate al titolare; promo applicabili anche dal commesso.
- Protezione modifiche a documenti non piu' in bozza e assegnazione utenti audit reporting.
- Protezione dei campi di totale vendita dalle modifiche CRUD dirette.
- Notifiche filtrate sul destinatario, inclusi dettagli e azioni.
- Schema autenticazione OpenAPI e registrazione drf-spectacular.

## Ancora da completare/verificare

- Contratti di input espliciti/OpenAPI per tutte le azioni: vari endpoint workflow usano ancora validazione manuale.
- Copertura test end-to-end di ogni azione e delle scritture concorrenti; i test degli elenchi non la sostituiscono.
- Cassa: aggiunte rimozione righe/pagamenti, ripristino saldo buoni, annullamento vendita aperta e registro audit. Righe con storico promozioni non eliminabili; nessuno storno POS esterno automatico.
- OCR: non presente un flusso di estrazione/approvazione risultati; richiede la scelta del provider.
- Collegamento fattura-ricevimenti: aggiunta azione `set-receipts`, solo in bozza e con ricevimenti confermati dello stesso fornitore.
- Report schedulati automatici: il modello conserva le impostazioni, ma manca il worker pianificato.
- Worker e pianificazione aggiornamento report/notifiche: i flag di configurazione da soli non eseguono job.
- Shopify reale: client HTTP, webhook firmati, elaborazione ordini e retry worker, oltre alla configurazione presente.
- Ulteriore controllo vincoli e immutabilita' sui CRUD generici (prezzi, conteggi avviati, configurazioni gia' utilizzate).

## Verifica eseguita

Python locale con le dipendenze del progetto e PostgreSQL su `127.0.0.1:5433`.
Docker non e' accessibile da questa sessione; nessuna migrazione sul database di sviluppo.
Schema OpenAPI: zero errori di generazione, restano avvisi sui nomi enum.
Comandi da usare anche in Docker: `manage.py check`, `manage.py test`, `manage.py spectacular --validate`.

## Nuove azioni di cassa e acquisti

- `POST sales/sales/{id}/remove-line/`: `line` (UUID), `reason`.
- `POST sales/sales/{id}/remove-payment/`: `payment` (UUID), `reason`.
- `POST sales/sales/{id}/cancel/`: `reason`; nessun pagamento residuo.
- `GET sales/sales/{id}/draft-changes/`: storico delle operazioni.
- `GET sales/lines/{id}/returnable-quantity/`: quantita' ancora restituibile, zero per vendite non confermate.
- `POST purchasing/invoices/{id}/set-receipts/`: `receipts` (lista UUID); sostituisce i collegamenti solo se compatibili con le righe.

Richiesta migrazione `sales.0004_saledraftchange`, non applicata automaticamente al database di sviluppo.
La rimozione del pagamento con carta e' una registrazione gestionale, non un rimborso eseguito dal POS.
