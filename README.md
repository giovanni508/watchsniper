# ⌚ WatchSniper

Sistema asincrono e scalabile per il monitoraggio del mercato degli orologi di lusso:
scraping continuo degli annunci, calcolo del valore di mercato (mediana dei prezzi attivi),
analisi dei margini e notifiche in tempo reale via **Telegram** e **dashboard web**.

## Architettura

```
 ┌──────────────┐   ScrapedListing   ┌──────────────┐   DealFoundEvent   ┌──────────────┐
 │   Scraper    │ ─────────────────▶ │   Analyzer   │ ─────────────────▶ │  Event Bus   │
 │ (Playwright) │    (repository)    │ (mediana +   │   (asyncio.Queue)  │              │
 └──────────────┘                    │  margini)    │                    └──────┬───────┘
        ▲                            └──────┬───────┘                           │
        │ loop periodico                    │                                   ▼
 ┌──────┴───────┐                    ┌──────▼───────┐                    ┌──────────────┐
 │  Scheduler   │                    │   SQLite     │ ◀───── FastAPI     │ Bot Telegram │
 │  (asyncio)   │                    │ (SQLAlchemy  │        /api/deals  │  (aiogram 3) │
 └──────────────┘                    │  2.0 async)  │        dashboard   └──────────────┘
                                     └──────────────┘
```

Tutti i componenti girano **nello stesso event loop** (`asyncio.TaskGroup` in `main.py`).

## Stack

- Python 3.12+, type hints ovunque
- SQLAlchemy 2.0 async + aiosqlite + Alembic
- Pydantic v2 + pydantic-settings (`.env`)
- Playwright async + BeautifulSoup4
- FastAPI + Jinja2 (dashboard)
- aiogram v3 (bot Telegram in polling)

## Setup

```bash
# 1. Dipendenze (richiede uv: https://docs.astral.sh/uv/)
uv sync

# 2. Browser per Playwright (necessario solo per scraper reali, non per il dummy)
uv run playwright install chromium

# 3. Configurazione
cp .env.example .env   # inserisci TELEGRAM_BOT_TOKEN (opzionale)

# 4. Avvio: API + bot + scheduler insieme
uv run python main.py
```

- Dashboard: <http://localhost:8000/>
- API docs: <http://localhost:8000/docs>

Senza `TELEGRAM_BOT_TOKEN` il bot viene disabilitato (warning nel log) e i deal
restano visibili su dashboard/API.

## Fonti di scraping

La/le fonte/i attive si scelgono via `SCRAPER_SOURCES` in `.env` (lista separata
da virgola):

| Valore | Descrizione |
|---|---|
| `dummy` (default) | Marketplace fittizio: popola la dashboard subito, **senza rete né browser**. Ideale per la demo locale. |
| `chrono24` | Scraper reale di Chrono24: richiede `uv run playwright install chromium` e accesso di rete (no proxy MITM). |
| `dummy,chrono24` | Entrambe le fonti a ogni ciclo. |

Per aggiungere una fonte: crea una sottoclasse di `BaseScraper` e registrala in
`SCRAPER_REGISTRY` (`app/scraper/scheduler.py`).

## Migrazioni

In sviluppo le tabelle sono create automaticamente all'avvio. Per ambienti gestiti:

```bash
uv run alembic revision --autogenerate -m "descrizione"
uv run alembic upgrade head
```

## Comandi del bot

| Comando | Effetto |
|---|---|
| `/start` | Registra l'utente e attiva gli alert |
| `/filtra prezzo 15000` | Alert solo per annunci sotto i 15.000€ |
| `/filtra margine 12` | Alert solo con margine ≥ 12% |

## API

| Endpoint | Descrizione |
|---|---|
| `GET /api/deals?max_price=&min_margin=` | Annunci attivi con margine > 10% |
| `GET /api/references` | Referenze tracciate e valori di mercato |
| `POST /api/filters` | Imposta i filtri utente (stessa logica del bot) |

## Formula del margine

```
Margine   = (Valore_di_Mercato − Prezzo_Annuncio) − Costi_Fissi_Stimati
Margine % = Margine / Prezzo_Annuncio × 100
```

`Valore_di_Mercato` = mediana dei prezzi degli annunci **attivi** della referenza.
I costi fissi sono configurabili via `ESTIMATED_FIXED_COSTS` in `.env`.

## Note legali

Lo scraper incluso (`DummyWatchScraper`) genera dati fittizi. Prima di puntare
`BaseScraper` su siti reali, verifica i Termini di Servizio e il `robots.txt`
del target e rispetta i rate limit.
