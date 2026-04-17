# Telegram Bot — Google Sheets Natural Language Query

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

A Telegram bot ([@Sanada1021bot](https://t.me/Sanada1021bot)) that answers plain-English questions about data stored in a Google Sheet.
The LLM **only translates** your question into a structured JSON query — all filtering, counting,
and aggregation is executed deterministically by **pandas**. No hallucinated numbers.

## Table of Contents

- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Example Queries](#example-queries)
- [Commands](#commands)
- [Configuration](#configuration)
- [Tech Stack](#tech-stack)
- [File Structure](#file-structure)

---

## Architecture

> **Key design principle: the LLM is a translator, not a calculator.**

```
┌──────────────────────────────────────────────────────────────────────┐
│                        User (Telegram)                               │
│   "Total Amount for Active customers in Phase 2"                     │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ plain-English text
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     QueryParser (LLM layer)                          │
│   Claude / Gemini / GPT-4  →  structured JSON only                  │
│                                                                      │
│   {                                                                  │
│     "action": "sum",                                                 │
│     "target_column": "Amount",                                       │
│     "filters": [                                                     │
│       {"column": "Status",  "op": "==", "value": "Active"},         │
│       {"column": "Phase",   "op": "==", "value": 2}                 │
│     ]                                                                │
│   }                                                                  │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ structured JSON
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        Validator                                     │
│   Checks: columns exist · types match · action is valid             │
│   Rejects bad queries before touching the sheet                     │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ validated + normalized query
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     SheetsHandler (pandas)                           │
│   1. Fetches Google Sheet (cached, TTL-based)                       │
│   2. Applies filters with pandas boolean indexing                   │
│   3. Computes aggregation (sum/avg/min/max/count/list)              │
│   Returns exact numbers — no LLM inference at this stage           │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ result dict
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      Reply formatter                                 │
│   Formats result as plain text or HTML table for Telegram           │
└──────────────────────────────────────────────────────────────────────┘
```

**Why this architecture matters for production use:**

- **Correctness** — pandas does all arithmetic. The LLM cannot hallucinate row counts or totals.
- **Safety** — the validator rejects queries with unknown columns or type mismatches *before* touching the sheet.
- **Speed** — sheet data is cached (configurable TTL); typical end-to-end response is under 3 seconds.
- **Cost-efficiency** — the LLM call is tiny (intent → one JSON object); no chain-of-thought tokens wasted on math.
- **Model-agnostic** — swapping the LLM provider only requires changing two config variables.

---

## Quick Start

No API keys needed — the bot falls back to built-in mock data automatically.

```bash
git clone https://github.com/Mpaycheck/tg-sheets-query-bot.git
cd tg-sheets-query-bot
pip install -r requirements.txt
python bot.py --demo
```

This runs 7 sample queries against mock data and prints results to stdout — great for a quick sanity check.

### Running the live Telegram bot

1. Copy `.env.template` to `.env` and fill in your credentials (see [Configuration](#configuration) below).
2. Start the bot:

```bash
python bot.py
```

The bot runs in polling mode. On the production GCP VM it is kept alive in a `screen` session:

```bash
screen -S tgbot
python bot.py
# Ctrl-A D to detach
screen -r tgbot   # to reattach
```

---

## Example Queries

| Query | Action | What it returns |
|---|---|---|
| `List customers in Phase 2 with Payment_Percent more than 60` | filter + list | matching rows as a table |
| `How many customers are in Phase 1?` | count | integer |
| `Total Amount for Active customers` | sum | numeric total |
| `Average Payment_Percent where Phase is 2` | avg | float |
| `Show customers in Region East` | filter + list | matching rows as a table |
| `Max Amount where Phase is 3` | max | numeric value |

The bot recognises these aggregation keywords: **sum / total**, **average / avg / mean**,
**min / minimum / lowest**, **max / maximum / highest**, **count / how many**.
Everything else defaults to a **list** (filtered row dump).

---

## Commands

| Command | Description |
|---|---|
| `/start` | Welcome message and list of available columns |
| `/help` | Full help text with example queries |
| `/status` | Bot uptime, total query count, last query time |
| `/history` | Last 5 queries and their results (in-memory, resets on restart) |

---

## Configuration

Copy `.env.template` → `.env`:

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `OPENAI_API_KEY` | API key for the LLM provider (OpenAI, Anthropic, etc.) |
| `OPENAI_MODEL` | Model name, e.g. `gpt-4o`, `claude-3-haiku-20240307` |
| `GOOGLE_SHEET_ID` | Spreadsheet ID from the sheet URL |
| `GOOGLE_CREDENTIALS_PATH` | Path to a GCP service-account JSON file |
| `SHEET_RANGE` | Cell range to read, e.g. `Sheet1!A:Z` |

If any credential is missing, the bot automatically enters **mock mode** using
built-in sample data — useful for local development and demos.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Bot framework | [python-telegram-bot](https://python-telegram-bot.org/) v20+ (async) |
| LLM parsing | OpenAI-compatible API (model is configurable) |
| Data execution | [pandas](https://pandas.pydata.org/) |
| Sheet access | Google Sheets API v4 |
| Runtime | Python 3.11+ / asyncio |
| Hosting | Google Cloud Platform — Compute Engine (asia-east1-a) |

---

## File Structure

```
bot.py              — Telegram entry point, command handlers, demo runner
query_parser.py     — LLM call → structured JSON (+ rule-based mock parser)
sheets_handler.py   — Google Sheets fetch + pandas query execution
validator.py        — Pre-execution sanity checks (columns, types, actions)
config.py           — Environment config with automatic mock-mode fallback
.env.template       — Copy this to .env and fill in your credentials
```
