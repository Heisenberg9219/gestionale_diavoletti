# Mappa funzionale del gestionale

Riferimento per il rifacimento del frontend (ramo `redesign`): ogni pagina nuova deve offrire **tutto** ciò che è elencato qui, con gli stessi nomi di menu e gli stessi indirizzi. Le migliorie si aggiungono, non tolgono nulla.

Generata dal codice del ramo `dev` (commit 4034793) analizzando titoli, pulsanti, campi, colonne, richieste di conferma, messaggi e chiamate al server di ogni pagina. Quando la versione nuova di una pagina è stata controllata voce per voce, si spunta *Verificato* nell'indice.

## Struttura comune

- **Accesso:** login con email e password, sessione che si rinnova da sola, uscita automatica dopo 20 minuti di inattività, pulsante Esci.
- **Menu laterale** a gruppi apribili; il commesso vede solo le pagine per cui ha il permesso.
- **Intestazione:** saluto con il nome utente, data, campanella delle notifiche con conteggio.
- **Indirizzi:** ogni pagina ha il proprio indirizzo; funzionano tasto indietro, preferiti e ricarica.
- **Finestre di conferma e di inserimento testo** del gestionale (non quelle del browser).

## Indice

| Gruppo | Pagina | Indirizzo | Verificato |
|---|---|---|---|
| Operatività | Panoramica | `/panoramica` | ☐ |
| Operatività | Storico vendite | `/storico-vendite` | ☐ |
| Operatività | Nuova vendita | `/nuova-vendita` | ☐ |
| Operatività | Cassa | `/cassa` | ☐ |
| Operatività | Resi | `/resi` | ☐ |
| Prodotti | Catalogo | `/catalogo` | ☐ |
| Prodotti | Magazzino | `/magazzino` | ☐ |
| Prodotti | Inventari | `/inventari` | ☐ |
| Prodotti | Riordini | `/riordini` | ☐ |
| Clienti | Clienti | `/clienti` | ☐ |
| Clienti | Fedeltà | `/fedelta` | ☐ |
| Clienti | Buoni | `/buoni` | ☐ |
| Clienti | Liste regalo | `/liste-regalo` | ☐ |
| Acquisti | Fornitori | `/fornitori` | ☐ |
| Acquisti | Ordini acquisto | `/ordini-acquisto` | ☐ |
| Marketing | Promozioni | `/promozioni` | ☐ |
| Gestione | Spese | `/spese` | ☐ |
| Gestione | Documenti e OCR | `/documenti` | ☐ |
| Gestione | Notifiche | `/notifiche` | ☐ |
| Controllo | Integrazioni | `/integrazioni` | ☐ |
| Controllo | Report | `/report` | ☐ |
| Controllo | Utenti e ruoli | `/utenti` | ☐ |

## Operatività

### Panoramica · `/panoramica`

File attuale: `frontend/src/pages/DashboardPage.jsx`

**Titoli e sezioni**
- Buongiorno, … .
- Scorte esaurite
- Tutto pronto per una buona giornata.
- Ultime vendite

**Pulsanti e azioni**
- Apri lista riordino
- Cassa
- Cerca
- Cerca articolo
- Chiudi menu
- Nuova vendita … Nuova vendita
- Nuova vendita … Vendite
- Storico vendite Vedi tutte
- Visualizza tutte

**Chiamate al server**
- `GET /notifications/deliveries/`
- `GET /notifications/notifications/`
- `GET /reporting/overview/`
- `POST /notifications/deliveries/{id}/mark-read/`

### Storico vendite · `/storico-vendite`

File attuale: `frontend/src/pages/SalesPage.jsx`

**Titoli e sezioni**
- Periodi preimpostati
- Seleziona periodo
- Storico vendite

**Pulsanti e azioni**
- Applica filtro
- Azzera
- Azzera filtri
- Chiudi
- Scarica CSV

**Campi e filtri**
- Cerca scontrino, cliente, marca, SKU o barcode
- Data fine
- Data inizio
- Tutti

**Messaggi mostrati**
- Non è stato possibile caricare lo storico vendite.

**Chiamate al server**
- `GET /catalog/brands/`
- `GET /catalog/categories/`
- `GET /catalog/seasons/`
- `GET /core/locations/`
- `GET /sales/registers/`
- `GET /sales/sales/`
- `GET /sales/sales/export-csv/`

### Nuova vendita · `/nuova-vendita`

File attuale: `frontend/src/pages/NewSalePage.jsx`

**Titoli e sezioni**
- Apri prima la cassa
- Articolo in lista regalo
- Associa cliente alla vendita
- Incassa la vendita
- Nuova vendita
- Pagamenti registrati
- Pagamento
- Scegli una lista
- Verifica della cassa

**Pulsanti e azioni**
- Aggiungi
- Annulla
- Annulla vendita
- Applica
- Applica sconto
- Arrotonda
- Associa cliente
- Carica lista regalo
- Cerca
- Chiudi
- Chiudi cambio
- Concludi vendita / Incassa e concludi
- Nessun contatto
- Rimuovi
- Saldo:
- Togli dalla lista e vendi
- Torna alla vendita
- Usa buono
- Vai al pagamento
- Vai alla cassa
- … Non disponibile

**Campi e filtri**
- 0.00 Dividi tra più metodi di pagamento
- Cerca o seleziona un buono
- Codice buono
- Contanti consegnati dal cliente €
- Es. 10
- Es. numero transazione
- Nome, telefono o codice cliente
- Pagamento carta €
- Pagamento contanti €
- Riferimento Facoltativo
- Scansiona barcode o cerca per SKU / nome
- Sconto %
- Sconto sul totale %
- Totale arrotondato €

**Conferme richieste**
- Annullare questa vendita e svuotare il carrello?
- Rimuovere il pagamento di …? Questa operazione rimuove la registrazione; eventuali contanti o pagamenti con carta vanno restituiti separatamente.

**Messaggi mostrati**
- Applica l'arrotondamento prima di incassare oppure ripristina il totale attuale.
- Articolo della lista … aggiunto al carrello.
- Articolo rimosso dal carrello.
- Buono applicato: ….
- Buono non trovato o non utilizzabile.
- Cliente associato: ….
- Contanti e carta devono coprire esattamente il residuo del totale, incluso l'arrotondamento applicato.
- I contanti ricevuti devono coprire la quota in contanti.
- Impossibile aggiungere l'articolo della lista:
- Impossibile annullare la vendita:
- Impossibile applicare il buono:
- Impossibile applicare l'arrotondamento:
- Impossibile applicare lo sconto:
- Impossibile associare il cliente:
- Impossibile caricare gli articoli della lista:
- Impossibile caricare le liste regalo:
- Impossibile preparare il pagamento:
- Impossibile rimuovere il pagamento:
- Impossibile rimuovere l'articolo:
- Indica i contanti ricevuti, almeno pari all'importo da registrare e con al massimo due decimali.
- Inserisci il codice del buono.
- Inserisci importi validi con al massimo due decimali.
- Inserisci un importo positivo, con al massimo due decimali.
- Inserisci un totale arrotondato valido, con al massimo due decimali.
- Inserisci uno sconto tra 0,01% e 100%, con al massimo due decimali.
- L'importo deve coprire esattamente il totale residuo.
- L'importo supera il residuo da pagare.
- Nessun altro pezzo disponibile nei magazzini.
- Non è stato possibile verificare la sessione di cassa. Controlla la connessione e ricarica la pagina.
- Pagamento non completato:
- Pagamento non completato: …. I pagamenti già registrati sono nel riepilogo.
- Questa riga della lista è già stata acquistata.
- Registra i pagamenti prima di concludere la vendita.
- Ricerca articoli non disponibile. Riprova.
- Ricerca clienti non disponibile:
- Rimuovi i pagamenti registrati, poi torna alla vendita e premi Annulla vendita.
- Vendita annullata.
- Vendita non conclusa:
- Vendita … registrata correttamente.

**Chiamate al server**
- `GET /catalog/variants/`
- `GET /customers/customers/`
- `GET /gift-lists/items/`
- `GET /gift-lists/lists/`
- `GET /sales/registers/`
- `GET /sales/sales/{id}/`
- `GET /sales/sessions/`
- `GET /vouchers/vouchers/`
- `GET /vouchers/vouchers/{id}/`
- `POST /sales/sales/`
- `POST /sales/sales/{id}/add-payment/`
- `POST /sales/sales/{id}/add-with-gift-check/`
- `POST /sales/sales/{id}/cancel/`
- `POST /sales/sales/{id}/confirm/`
- `POST /sales/sales/{id}/remove-line/`
- `POST /sales/sales/{id}/remove-payment/`
- `POST /sales/sales/{id}/set-customer/`
- `POST /sales/sales/{id}/set-line/`
- `POST /sales/sales/{id}/set-total/`
- `POST /vouchers/vouchers/{id}/redeem/`

### Cassa · `/cassa`

File attuale: `frontend/src/pages/CashPage.jsx`

**Titoli e sezioni**
- Apri una sessione di cassa
- Cassa
- Chiudi la cassa

**Pulsanti e azioni**
- Apertura... / Apri cassa
- Chiusura... / Conferma chiusura
- Creazione... / Crea registratore
- Nuova vendita … Nuova vendita

**Campi e filtri**
- 0,00
- Codice registratore
- Contante contato
- Fondo iniziale
- Nome registratore
- Registratore … Seleziona registratore
- Sede … Seleziona sede

**Messaggi mostrati**
- Non è stato possibile caricare la situazione della cassa.

**Chiamate al server**
- `GET /core/locations/`
- `GET /sales/registers/`
- `GET /sales/sessions/`
- `POST /sales/registers/`
- `POST /sales/sessions/open/`
- `POST /sales/sessions/{id}/close/`

### Resi · `/resi`

File attuale: `frontend/src/pages/ReturnsPage.jsx`

**Titoli e sezioni**
- Apri un nuovo reso
- Articoli restituiti
- Resi
- Reso in bozza
- Trova la vendita originale

**Pulsanti e azioni**
- Annulla bozza
- Annulla reso
- Cambia vendita
- Cerca
- Chiudi
- Completa reso e genera buono
- Conferma annullamento
- Conferma e fai il cambio
- Conferma reso e genera buono
- Indietro
- Nuova vendita … Avvia un cambio
- Ricerca
- Torna allo storico
- Vendita banco

**Campi e filtri**
- Acquistati: … · già restituito / · restituibili:
- Cerca reso, scontrino, cliente o articolo
- Cerca vendita o articolo
- Es. reso registrato per errore
- Motivo del reso
- Motivo dell'annullamento

**Messaggi mostrati**
- Inserisci il motivo del reso.
- Non è stato possibile caricare lo storico resi.
- Ricerca vendite non disponibile.
- Scrivi il motivo dell'annullamento.
- Seleziona almeno un articolo da restituire.

**Chiamate al server**
- `GET /returns/lines/`
- `GET /returns/returns/`
- `GET /sales/lines/{id}/returnable-quantity/`
- `GET /sales/sales/`
- `GET /sales/sales/{id}/`
- `GET /vouchers/vouchers/{id}/`
- `POST /returns/returns/create-draft/`
- `POST /returns/returns/{id}/cancel/`
- `POST /returns/returns/{id}/confirm/`
- `POST /returns/returns/{id}/set-line/`

## Prodotti

### Catalogo · `/catalogo`

File attuale: `frontend/src/pages/CatalogPage.jsx`

**Titoli e sezioni**
- Catalogo
- Modifica articolo / Nuovo articolo

**Pulsanti e azioni**
- Annulla
- Applica modifiche
- Cancella selezionati
- Generazione SKU... / Salva modifiche
- Nuovo articolo
- Ricerca
- Scarica CSV

**Campi e filtri**
- 0,00
- Anno collezione
- Barcode
- Categoria
- Cerca nome, SKU, barcode o codice prodotto
- Codice prodotto
- Colore
- Descrizione
- IVA
- Marca
- Nome prodotto
- Non modificare
- Prezzo di acquisto
- Prezzo vendita
- Quantità da caricare
- Sede del carico
- SKU
- Taglia
- Tipo collezione

**Conferme richieste**
- Nome
- Vuoi cancellare … righe dal catalogo? Le varianti saranno archiviate e non più visibili.

**Messaggi mostrati**
- Seleziona almeno un valore da modificare.

**Chiamate al server**
- `DELETE /catalog/barcodes/{id}/`
- `GET /catalog/barcodes/`
- `GET /catalog/brands/`
- `GET /catalog/categories/`
- `GET /catalog/colors/`
- `GET /catalog/products/{id}/`
- `GET /catalog/seasons/`
- `GET /catalog/sizes/`
- `GET /catalog/variants/`
- `GET /catalog/variants/export-csv/`
- `GET /core/locations/`
- `GET /core/settings/`
- `GET /core/tax-rates/`
- `GET /pricing/sale-prices/`
- `PATCH /catalog/products/{id}/`
- `PATCH /catalog/variants/{id}/`
- `POST /catalog/products/`
- `POST /catalog/seasons/`
- `POST /catalog/variants/`
- `POST /catalog/variants/bulk-archive/`
- `POST /catalog/variants/bulk-update/`
- `POST /catalog/variants/reserve-skus/`
- `POST /catalog/variants/{id}/initial-stock/`
- `POST /pricing/sale-prices/`

### Magazzino · `/magazzino`

File attuale: `frontend/src/pages/InventoryPage.jsx`

**Titoli e sezioni**
- Magazzino

**Pulsanti e azioni**
- Ricerca

**Campi e filtri**
- Cerca SKU, articolo o sede

**Conferme richieste**
- Motivo della rettifica:
- Nuova quantità fisica:

**Messaggi mostrati**
- Inserisci una quantità intera maggiore o uguale a zero.
- Non è stato possibile caricare le giacenze.
- Rettifica registrata nello storico movimenti.

**Chiamate al server**
- `GET /inventory/stock/`
- `POST /inventory/movements/adjust/`

### Inventari · `/inventari`

File attuale: `frontend/src/pages/CountsPage.jsx`

**Titoli e sezioni**
- Inventari
- Personalizza l'inventario / Apri un inventario

**Pulsanti e azioni**
- Annulla
- Nuovo inventario
- Salva modifiche / Avvia inventario

**Campi e filtri**
- Categoria
- Collezione
- Fornitore
- Marca
- Nome inventario
- Sede … Seleziona sede
- Tipo … Tutto il catalogoInventario personalizzato

**Messaggi mostrati**
- Copia creata in bozza: puoi modificarla prima di avviarla.
- Inventario creato e avviato.
- Inventario eliminato definitivamente.
- Inventario in bozza aggiornato.
- Per un inventario parziale scegli almeno un filtro.
- Prima crea almeno un articolo con variante nel Catalogo.
- Seleziona una sede.

**Chiamate al server**
- `DELETE /inventory/counts/{id}/`
- `GET /catalog/brands/`
- `GET /catalog/categories/`
- `GET /catalog/seasons/`
- `GET /catalog/variants/`
- `GET /core/locations/`
- `GET /inventory/counts/`
- `GET /inventory/counts/{id}/export-csv/`
- `GET /suppliers/suppliers/`
- `PATCH /inventory/counts/{id}/`
- `POST /inventory/counts/`
- `POST /inventory/counts/{id}/duplicate/`
- `POST /inventory/counts/{id}/start/`

### Riordini · `/riordini`

File attuale: `frontend/src/pages/ReordersPage.jsx`

**Titoli e sezioni**
- Riordini

**Pulsanti e azioni**
- Aggiungi
- Aggiungi articolo
- Ricerca

**Campi e filtri**
- Avvisami
- Cerca articolo o SKU
- Cerca nel magazzino per articolo o SKU

**Conferme richieste**
- Motivo della rimozione:

**Messaggi mostrati**
- Impossibile caricare i riordini.

**Chiamate al server**
- `GET /inventory/stock/`
- `GET /reorders/items/`
- `POST /reorders/items/add/`
- `POST /reorders/items/refresh-notifications/`
- `POST /reorders/items/{id}/remove/`
- `POST /reorders/items/{id}/update-pending/`

## Clienti

### Clienti · `/clienti`

File attuale: `frontend/src/pages/CustomersPage.jsx`

**Titoli e sezioni**
- Anagrafica clienti
- Modifica cliente / Registra un cliente

**Pulsanti e azioni**
- Annulla
- Deseleziona
- Elimina
- Nuovo cliente
- Ricerca
- Salva modifiche / Registra cliente
- Scarica CSV

**Campi e filtri**
- Cerca codice, nome, cognome, email o telefono
- Città
- Cognome
- Data di nascita
- Email
- Nome
- Telefono

**Messaggi mostrati**
- Cliente eliminato correttamente.
- Clienti eliminati correttamente.

**Chiamate al server**
- `DELETE /customers/customers/{id}/`
- `GET /customers/customers/`

### Fedeltà · `/fedelta`

File attuale: `frontend/src/pages/LoyaltyPage.jsx`

**Titoli e sezioni**
- Fedeltà

**Pulsanti e azioni**
- Annulla
- Attiva per tutti
- Crea premio
- Emetti al cliente
- Emetti premio
- Nuova raccolta
- Nuovo premio
- Promo per tutti
- Ricerca
- Salva modifiche / Crea raccolta

**Campi e filtri**
- Cerca cliente per nome, cognome o codice
- Cliente selezionato … Seleziona cliente
- Costo punti
- Fine
- Fine facoltativa
- Inizio
- Nome premio
- Nome promozione
- Nome raccolta
- Percentuale
- Premio personale … Seleziona premio
- Punti assegnati
- Scadenza giorni
- Sconto percentuale
- Spesa ogni €
- Tipo … Sconto in euroSconto percentuale
- Valore €

**Messaggi mostrati**
- Premio fedeltà creato correttamente.
- Premio personale emesso correttamente.
- Promozione automatica attivata per tutti i clienti.
- Raccolta punti creata e attivata.
- Raccolta punti disattivata.
- Raccolta punti modificata correttamente.

**Chiamate al server**
- `DELETE /loyalty/earning-rules/{id}/`
- `GET /customers/customers/`
- `GET /loyalty/earning-activations/`
- `GET /loyalty/earning-rules/`
- `GET /loyalty/point-movements/balance/`
- `GET /loyalty/reward-definitions/`
- `PATCH /loyalty/earning-rules/{id}/`
- `POST /loyalty/earning-activations/activate/`
- `POST /loyalty/earning-rules/`
- `POST /loyalty/issued-rewards/issue/`
- `POST /loyalty/reward-definitions/`
- `POST /promotions/campaigns/`
- `POST /promotions/campaigns/{id}/activate/`
- `POST /promotions/offers/`
- `POST /promotions/rules/`

### Buoni · `/buoni`

File attuale: `frontend/src/pages/VoucherPage.jsx`

**Titoli e sezioni**
- Buoni
- Emetti un buono regalo

**Pulsanti e azioni**
- Annulla
- Cambia cliente
- Deseleziona
- Emetti buono
- Emissione... / Emetti buono
- Ricerca
- Scarica CSV

**Campi e filtri**
- 0,00
- Avvisami alla scadenza
- Cerca cliente per cognome
- Cerca codice, nome o cognome
- Cognome intestatario
- Facoltative
- Facoltativo
- Incasso … Contanti (entra in cassa)CartaAltroOmaggio, nessun incasso
- Inizia a scrivere il cognome
- Nome intestatario
- Note
- Scadenza
- Valore iniziale

**Messaggi mostrati**
- Buoni annullati correttamente.
- Buono emesso correttamente.
- Cerca e seleziona un cliente prima di emettere il buono.

**Chiamate al server**
- `GET /customers/customers/`
- `GET /vouchers/vouchers/`
- `POST /vouchers/vouchers/issue/`
- `POST /vouchers/vouchers/{id}/cancel/`

### Liste regalo · `/liste-regalo`

File attuale: `frontend/src/pages/GiftListsPage.jsx`

**Titoli e sezioni**
- Articoli della lista
- Conferenti
- Crea una lista regalo
- Dettaglio lista
- Liste regalo

**Pulsanti e azioni**
- Aggiungi conferente
- Aggiungi dal catalogo
- Annulla
- Chiudi lista
- Creazione... / Crea lista
- Deseleziona
- Elimina
- Nuova lista
- Ricerca
- Salvataggio… / Aggiungi alla lista (… )
- Salvataggio… / Salva conferente
- Scarica CSV

**Campi e filtri**
- 0,00
- Avvisami per questa lista
- Cerca lista o beneficiario
- Cerca nome, SKU, taglia o colore
- Cliente registrato … Non associare un cliente
- Cognome
- Cognome beneficiario
- Data evento
- Email
- Es. Lista nascita Rossi
- Facoltative
- Importo (€)
- Modalità … ArticoliContributi
- Nome
- Nome beneficiario
- Note
- Pagamento
- Quantità
- Sede … Seleziona sede
- Seleziona tutti i risultati
- Telefono
- Tipo … Lista nascitaLista compleanno
- Titolo lista

**Colonne delle tabelle**
- Acquistati
- Articolo
- Cognome
- Importo
- Nome
- Pagamento
- Richiesti
- Riservati

**Messaggi mostrati**
- Inserisci nome e cognome del conferente.
- Inserisci un importo maggiore di zero, con massimo due decimali.
- Lista creata. Aggiornamento notifiche non riuscito:
- Lista regalo creata correttamente.
- Liste regalo eliminate correttamente.

**Chiamate al server**
- `DELETE /gift-lists/lists/{id}/`
- `GET /catalog/variants/`
- `GET /catalog/variants/{id}/`
- `GET /core/locations/`
- `GET /customers/customers/`
- `GET /gift-lists/lists/`
- `GET /gift-lists/lists/{id}/`
- `GET /gift-lists/{id}/`
- `POST /gift-lists/lists/`
- `POST /gift-lists/lists/refresh-notifications/`
- `POST /gift-lists/lists/{id}/add-contribution/`
- `POST /gift-lists/lists/{id}/add-items/`
- `POST /gift-lists/lists/{id}/close/`

## Acquisti

### Fornitori · `/fornitori`

File attuale: `frontend/src/pages/SuppliersPage.jsx`

**Titoli e sezioni**
- Aggiorna l'anagrafica / Registra un fornitore
- Fornitori

**Pulsanti e azioni**
- Annulla
- Nuovo fornitore
- Ricerca
- Salva modifiche / Crea fornitore

**Campi e filtri**
- CAP
- Cerca codice, ragione sociale, partita IVA, email o telefono
- Città
- Codice fiscale
- Codice fornitore
- Codice SDI
- Email
- Es. 30 giorni data fattura
- Facoltative
- Indirizzo
- Note
- Partita IVA
- PEC
- Provincia
- Ragione sociale
- Stato … AttivoInattivo
- Telefono
- Termini di pagamento

**Messaggi mostrati**
- Fornitore eliminato correttamente.

**Chiamate al server**
- `DELETE /suppliers/suppliers/{id}/`
- `GET /suppliers/suppliers/`

### Ordini acquisto · `/ordini-acquisto`

File attuale: `frontend/src/pages/PurchaseOrdersPage.jsx`

**Titoli e sezioni**
- Ordini acquisto
- Prepara una bozza

**Pulsanti e azioni**
- Aggiungi riga
- Annulla
- Creazione... / Crea bozza
- Invia
- Nuovo ordine
- Ricerca

**Campi e filtri**
- Cerca numero ordine o note
- Consegna prevista
- Costo unit.
- Data ordine
- Facoltative
- Fornitore … Seleziona fornitore
- Note

**Messaggi mostrati**
- Aggiungi almeno un articolo all'ordine.
- Ordine in bozza creato correttamente.
- Ordine inviato al fornitore.

**Chiamate al server**
- `GET /catalog/variants/`
- `GET /purchasing/orders/`
- `GET /suppliers/suppliers/`
- `POST /purchasing/order-lines/`
- `POST /purchasing/orders/`
- `POST /purchasing/orders/{id}/send/`

## Marketing

### Promozioni · `/promozioni`

File attuale: `frontend/src/pages/PromotionsPage.jsx`

**Titoli e sezioni**
- Crea una promozione
- Promozioni

**Pulsanti e azioni**
- Annulla
- Creazione... / Crea e attiva
- Nuova promozione
- Termina

**Campi e filtri**
- Cerca promozione o codice
- Es. Saldi autunno
- Facoltative
- Fine
- Inizio
- Marca … Tutto il catalogo
- Nome promozione
- Note
- Sconto % / Sconto €
- Tipo campagna … PromozioneSaldi
- Tipo sconto … PercentualeImporto fisso

**Messaggi mostrati**
- Imposta una data di fine per la promozione.
- La data di fine deve essere successiva all'inizio.
- Promozione creata e attivata per tutti i clienti.
- Promozione terminata correttamente.

**Chiamate al server**
- `GET /catalog/brands/`
- `GET /promotions/activations/`
- `GET /promotions/campaigns/`
- `GET /promotions/offer-brands/`
- `GET /promotions/offers/`
- `GET /promotions/rules/`
- `POST /promotions/activations/{id}/end/`
- `POST /promotions/campaigns/`
- `POST /promotions/campaigns/{id}/activate/`
- `POST /promotions/offer-brands/`
- `POST /promotions/offers/`
- `POST /promotions/rules/`

## Gestione

### Spese · `/spese`

File attuale: `frontend/src/pages/ExpensesPage.jsx`

**Titoli e sezioni**
- Registra una spesa
- Spese

**Pulsanti e azioni**
- Aggiungi
- Annulla
- Deseleziona
- Elimina
- Registra spesa
- Registrazione...
- Segna come pagate

**Campi e filtri**
- Avvisami alla scadenza
- Categoria … Seleziona categoria… +
- Cerca una spesa
- Data documento
- Descrizione
- Es. Bolletta elettrica
- Es. Utenze
- Facoltative
- Importo €
- Note
- Nuova categoria … Aggiungi
- Scadenza

**Messaggi mostrati**
- Categoria creata correttamente.
- Inserisci il nome della categoria.
- Puoi eliminare soltanto spese non ancora pagate.
- Seleziona almeno una spesa da pagare.
- Spese selezionate eliminate correttamente.
- Spese selezionate segnate come pagate.

**Chiamate al server**
- `GET /expenses/categories/`
- `GET /expenses/expenses/`
- `POST /expenses/categories/`
- `POST /expenses/expenses/`
- `POST /expenses/expenses/refresh-due-notifications/`
- `POST /expenses/expenses/{id}/add-payment/`
- `POST /expenses/expenses/{id}/cancel/`
- `POST /expenses/expenses/{id}/open/`

### Documenti e OCR · `/documenti`

File attuale: `frontend/src/pages/DocumentsOcrPage.jsx`

**Titoli e sezioni**
- Carica un PDF
- Dettaglio fattura caricata in magazzino / Controlla e registra la fattura
- Documenti e OCR

**Pulsanti e azioni**
- Aggiungi riga
- Aggiungi taglia
- Annulla
- Applica ricarico
- Cancellazione... / Cancella selezionati
- Carica documento
- Caricamento...
- Chiudi
- Deseleziona
- documents/attachments/… /download
- Generazione SKU... / Conferma e carica in magazzino
- Ricalcola importi dalle righe incluse
- Salva proposta
- Scegli file
- Usa quantità riga:

**Campi e filtri**
- Aliquota IVA articolo … Seleziona aliquota
- Anno collezione
- Categoria … Seleziona
- Cerca documento, numero o fornitore
- Codice a barre
- Colore … Nessuno
- Data
- Data documento
- Destinazione carico … Seleziona sede
- File PDF … Scegli file Nessun file selezionato
- Fornitore
- Fornitore in rubrica … Seleziona fornitore
- Imponibile articoli
- Includi articolo
- IVA %
- Marca predefinita … Seleziona marca
- Marca … Nessuna
- Nome nuovo prodotto
- Numero documento
- Numero fattura
- Prezzo vendita … Applica ricarico
- Prodotto esistente … Crea nuovo prodotto
- Quantità
- SKU
- Taglia … Seleziona
- Tipo collezione … Seleziona collezionePrimavera/EstateAutunno/Inverno
- Tipo documento … Seleziona tipo
- Titolo
- Totale fattura

**Conferme richieste**
- Cancellare … selezionati?
- Nome del nuovo colore
- Nome della nuova categoria
- Nome della nuova marca

**Messaggi mostrati**
- Analisi OCR completata. Apri la proposta per controllare gli articoli.
- Analisi OCR in corso: puoi continuare a lavorare, il risultato comparirà qui.
- Articoli caricati in magazzino correttamente.
- correttamente.
- Documento e PDF caricati. Avvia l'OCR per preparare la proposta.
- Il caricamento in magazzino non è avvenuto:
- Il caricamento in magazzino non è avvenuto: correggi i campi evidenziati.
- Il ricalcolo non è avvenuto: ….
- Impossibile cancellare i documenti:
- Impossibile caricare i documenti:
- Impossibile generare gli SKU:
- Impossibile generare lo SKU:
- Impossibile preparare la proposta:
- L'analisi OCR sta richiedendo più tempo del previsto. Ricarica la pagina tra qualche minuto.
- La bozza non è stata salvata:
- Seleziona un PDF da allegare.

**Chiamate al server**
- `GET /documents/attachments/{id}/download/`
- `GET /documents/ocr-analyses/{id}/`
- `GET {id}{id}page={id}&page_size=200`
- `POST /catalog/brands/`
- `POST /catalog/categories/`
- `POST /catalog/colors/`
- `POST /catalog/variants/reserve-skus/`
- `POST /documents/attachments/{id}/analyze-invoice/`
- `POST /documents/attachments/{id}/validate-review/`
- `POST /documents/documents/`
- `POST /documents/documents/cancel-selected/`
- `POST /documents/documents/{id}/upload-attachment/`
- `POST /documents/ocr-analyses/{id}/apply-purchase-proposal/`
- `POST /documents/ocr-analyses/{id}/save-purchase-proposal/`

### Notifiche · `/notifiche`

File attuale: `frontend/src/pages/NotificationsPage.jsx`

**Titoli e sezioni**
- Notifiche

**Pulsanti e azioni**
- Deseleziona
- Elimina

**Campi e filtri**
- Cerca nelle notifiche

**Messaggi mostrati**
- Notifica archiviata.
- Notifica risolta correttamente.

**Chiamate al server**
- `GET /notifications/deliveries/`
- `GET /notifications/notifications/`
- `POST /notifications/deliveries/{id}/archive/`
- `POST /notifications/deliveries/{id}/mark-read/`
- `POST /notifications/notifications/{id}/resolve/`

## Controllo

### Integrazioni · `/integrazioni`

File attuale: `frontend/src/pages/IntegrationsPage.jsx`

**Titoli e sezioni**
- Collega Shopify
- Integrazioni
- Ultime sincronizzazioni

**Pulsanti e azioni**
- Annulla
- Configura
- Elimina
- Nuova integrazione
- Salva modifiche / Crea integrazione

**Campi e filtri**
- Codice
- Dominio Shopify
- Es. Shop online
- Integrazione attiva
- negozio.myshopify.com
- Nome integrazione
- Prefisso credenziali
- Sede vendite online … Non impostata
- SHOP_ONLINE
- SHOPIFY
- Versione API

**Conferme richieste**
- Eliminare l'integrazione “…”?

**Messaggi mostrati**
- Integrazione eliminata correttamente.

**Chiamate al server**
- `DELETE /integrations/connections/{id}/`
- `GET /core/locations/`
- `GET /integrations/connections/`
- `GET /integrations/sync-events/`
- `PATCH /integrations/connections/{id}/`

### Report · `/report`

File attuale: `frontend/src/pages/ReportsPage.jsx`

**Titoli e sezioni**
- Configura un indicatore
- Report

**Pulsanti e azioni**
- Aggiorna
- Annulla
- Creazione... / Crea report
- Nuovo report

**Campi e filtri**
- Confronta periodo precedente
- Es. Incassi mensili
- Metrica
- Periodo
- Raggruppa per
- Titolo
- Visualizzazione … ValoreIstogrammaLineaTabella

**Conferme richieste**
- Eliminare il report “…”?

**Messaggi mostrati**
- Report aggiornato correttamente.
- Report creato correttamente.
- Report eliminato correttamente.

**Chiamate al server**
- `DELETE /reporting/widgets/{id}/`
- `GET /reporting/dashboards/`
- `GET /reporting/widgets/`
- `GET /reporting/widgets/{id}/calculate/`
- `GET /reporting/widgets/{id}/export-csv/`
- `POST /reporting/dashboards/`
- `POST /reporting/widgets/`
- `POST /reporting/widgets/{id}/refresh/`

### Utenti e ruoli · `/utenti`

File attuale: `frontend/src/pages/UsersRolesPage.jsx`

**Titoli e sezioni**
- Aggiorna accesso / Crea un accesso
- Utenti e ruoli

**Pulsanti e azioni**
- Annulla
- Archivia
- Attiva
- Blocca
- Deseleziona
- Nuovo utente
- Salva modifiche / Crea utente
- Salva permessi

**Campi e filtri**
- Cognome
- Email
- Nome
- Password (lascia vuoto per non cambiarla) … Non modificata / Almeno 8 caratteri
- Ruolo

**Conferme richieste**
- Archiviare gli utenti selezionati?

**Messaggi mostrati**
- Permessi del commesso salvati correttamente.
- Utenti archiviati correttamente.

**Chiamate al server**
- `DELETE /auth/users/{id}/`
- `GET /auth/roles/`
- `GET /auth/users/`
- `GET /auth/users/{id}/page-permissions/`
- `PATCH /auth/users/{id}/`
- `PATCH /auth/users/{id}/page-permissions/`
