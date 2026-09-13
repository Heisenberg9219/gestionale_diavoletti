# Attivita da completare

## Deploy server

- Configurare un job cron giornaliero sul server di produzione che esegua il comando Django `generate_notifications` nel container backend. Il job deve generare avvisi solo per i record con `notifications_enabled=true`.
