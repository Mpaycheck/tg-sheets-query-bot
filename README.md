# Telegram Bot — Google Sheets Natural Language Query

A Telegram bot that answers plain-English questions about a Google Sheet.
The LLM **only parses** the question into a structured query — all filtering,
counting, and aggregation is done deterministically with pandas.

## Quick start (no API keys needed)

```bash
pip install -r requirements.txt
python bot.py --demo
```

## Architecture

```
user text → QueryParser (OpenAI → JSON) → Validator → SheetsHandler (pandas) → reply
```

- `bot.py` — Telegram entry point + offline demo runner
- `query_parser.py` — LLM call, returns structured JSON only
- `sheets_handler.py` — Google Sheets fetch + pandas execution
- `validator.py` — rejects bad queries before execution
- `config.py` — auto mock-mode when keys are missing

## Example queries

- `List customers in Phase 2 with Payment_Percent more than 60`
- `How many customers are in Phase 1?`
- `Total Amount for Active customers`
- `Max Amount in Phase 3`

## Why this architecture

- **Correctness:** pandas does the math. LLM never generates numbers.
- **Safe:** validator rejects unknown columns or wrong types before execution.
- **Fast:** sheet data is cached, replies under 3–5 seconds.
