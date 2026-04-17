import logging
import sys
import time
from collections import deque
from datetime import datetime

from config import Config
from query_parser import QueryParser
from sheets_handler import SheetsHandler
from validator import validate

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
log = logging.getLogger('bot')

# Maximum number of recent queries kept in memory for /history
HISTORY_LIMIT = 5


class QueryPipeline:
    """Ties together parsing, validation, and sheet execution for one query."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.sheets = SheetsHandler(
            cfg.google_sheet_id,
            cfg.google_credentials_path,
            cfg.sheet_range,
            cfg.cache_ttl_seconds,
            cfg.mock_mode,
        )
        self.parser = QueryParser(cfg.openai_api_key, cfg.openai_model, cfg.mock_mode)

        # Runtime statistics (reset on each process restart)
        self.startup_time: float = time.time()
        self.query_count: int = 0
        self.last_query_time: float | None = None
        # Circular buffer of recent queries for /history
        self.history: deque = deque(maxlen=HISTORY_LIMIT)

    def answer(self, user_text: str) -> str:
        """Process a natural-language query end-to-end and return a reply string."""
        t0 = time.time()
        columns, dtypes = self.sheets.schema()

        # --- Step 1: LLM parses the question into a structured JSON query ---
        try:
            parsed = self.parser.parse(user_text, columns)
        except Exception as e:
            log.warning('Parse error for %r: %s', user_text, e)
            return (
                "\u26a0\ufe0f I couldn't understand that query.\n"
                "Try rephrasing it, or type /help to see usage examples."
            )

        # --- Step 2: Validator rejects bad columns or unsupported operations ---
        result = validate(parsed, columns, dtypes)
        if not result.ok:
            # Surface column-name errors with the full column list as a hint
            if any('column' in err.lower() for err in result.errors):
                return (
                    "\u26a0\ufe0f Couldn't find that column.\n"
                    f"Available columns: <code>{', '.join(columns)}</code>\n\n"
                    "Type /help for usage examples."
                )
            return (
                "\u26a0\ufe0f Query error:\n"
                + "\n".join(f"\u2022 {e}" for e in result.errors)
                + "\n\nType /help for usage examples."
            )

        # --- Step 3: pandas executes the query against the sheet data ---
        try:
            output = self.sheets.execute(result.normalized_query)
        except Exception as e:
            log.error('Execution error for %r: %s', user_text, e)
            return (
                "\u26a0\ufe0f Something went wrong while reading the sheet.\n"
                "Please try again in a moment."
            )

        elapsed = time.time() - t0
        log.info('query completed in %.2fs', elapsed)

        reply = _format(output)

        # Update runtime statistics
        self.query_count += 1
        self.last_query_time = time.time()
        # Keep a short snippet for /history display
        snippet = reply[:200] + ('\u2026' if len(reply) > 200 else '')
        self.history.append({
            'text': user_text,
            'snippet': snippet,
            'ts': datetime.now().strftime('%H:%M:%S'),
        })

        return reply


def _format(output: dict) -> str:
    """Convert a SheetsHandler result dict into a human-readable reply."""
    a = output.get('action')

    if a == 'count':
        return f"Count: {output['value']} row(s) match."

    if a in ('sum', 'avg', 'min', 'max'):
        v = output.get('value')
        if v is None:
            return f"No numeric data found for {a}."
        label = {'sum': 'Total', 'avg': 'Average', 'min': 'Minimum', 'max': 'Maximum'}[a]
        return (
            f"{label} {output.get('target_column', '')}: {v:,.2f} "
            f"(from {output.get('row_count', 0)} row(s))"
        )

    if a == 'list':
        rows = output.get('rows', [])
        if not rows:
            return (
                "No rows match those filters.\n"
                "Try broadening your query, or type /help for examples."
            )
        hdr = list(rows[0].keys())
        lines = [' | '.join(hdr), '-' * 40]
        for r in rows[:20]:
            lines.append(' | '.join(str(r.get(h, '')) for h in hdr))
        suffix = '' if len(rows) <= 20 else f'\n\u2026 and {len(rows) - 20} more'
        table = '\n'.join(lines) + suffix
        return f'Matched {len(rows)} row(s):\n<pre>{table}</pre>'

    return str(output)


def run_demo(pipeline: QueryPipeline):
    """Run a batch of sample queries against mock data and print to stdout."""
    for q in [
        'List customers in Phase 2 with Payment_Percent more than 60',
        'How many customers are in Phase 1?',
        'Total Amount where Phase is 2',
        'Average Payment_Percent where Phase is 2',
        'Show customers in Region East',
        'List customers where Status is Paused',
        'Max Amount where Phase is 3',
    ]:
        print(f'Q: {q}\n{pipeline.answer(q)}\n' + '-' * 60)


def run_telegram(pipeline: QueryPipeline):
    """Start the Telegram bot (blocking — runs until Ctrl-C)."""
    import asyncio
    from telegram import Update
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

    # ------------------------------------------------------------------ /start

    async def cmd_start(update: Update, _ctx):
        """Welcome message and column list."""
        cols, _ = pipeline.sheets.schema()
        await update.message.reply_text(
            "\U0001f44b Hi! I answer plain-English questions about your Google Sheet.\n\n"
            f"Available columns: {', '.join(cols)}\n\n"
            "Type /help to see what I can do."
        )

    # ------------------------------------------------------------------ /help

    async def cmd_help(update: Update, _ctx):
        """Full help text with example queries."""
        cols, _ = pipeline.sheets.schema()
        text = (
            "\U0001f916 <b>Sheets Query Bot \u2014 Help</b>\n\n"
            "<b>How it works:</b>\n"
            "Send me a plain-English question and I'll query your Google Sheet. "
            "The AI only translates your words into a structured query \u2014 all "
            "filtering and math is done by pandas, so the results are always exact.\n\n"
            "<b>Commands:</b>\n"
            "/start   \u2014 welcome message + column list\n"
            "/help    \u2014 this message\n"
            "/status  \u2014 uptime, query count, last query time\n"
            "/history \u2014 last 5 queries and their results\n\n"
            f"<b>Available columns:</b> <code>{', '.join(cols)}</code>\n\n"
            "<b>Example queries:</b>\n"
            "\u2022 <i>List customers in Phase 2 with Payment_Percent more than 60</i>\n"
            "\u2022 <i>How many customers are in Phase 1?</i>\n"
            "\u2022 <i>Total Amount for Active customers</i>\n"
            "\u2022 <i>Average Payment_Percent where Phase is 2</i>\n"
            "\u2022 <i>Show customers in Region East</i>\n"
            "\u2022 <i>Max Amount where Phase is 3</i>"
        )
        await update.message.reply_text(text, parse_mode='HTML')

    # ------------------------------------------------------------------ /status

    async def cmd_status(update: Update, _ctx):
        """Report uptime, query count, and time of last query."""
        uptime_secs = int(time.time() - pipeline.startup_time)
        h, remainder = divmod(uptime_secs, 3600)
        m, s = divmod(remainder, 60)
        uptime_str = f"{h}h {m}m {s}s"

        if pipeline.last_query_time:
            last_str = datetime.fromtimestamp(pipeline.last_query_time).strftime(
                '%Y-%m-%d %H:%M:%S'
            )
        else:
            last_str = 'no queries yet'

        text = (
            "\U0001f4ca <b>Bot Status</b>\n\n"
            f"\u2022 Uptime: {uptime_str}\n"
            f"\u2022 Queries handled: {pipeline.query_count}\n"
            f"\u2022 Last query: {last_str}"
        )
        await update.message.reply_text(text, parse_mode='HTML')

    # ------------------------------------------------------------------ /history

    async def cmd_history(update: Update, _ctx):
        """Show the last HISTORY_LIMIT queries with timestamps and result snippets."""
        if not pipeline.history:
            await update.message.reply_text(
                "No queries yet \u2014 ask me something first!\n"
                "Type /help for examples."
            )
            return

        lines = ["\U0001f4dc <b>Recent Queries</b>\n"]
        for i, entry in enumerate(reversed(pipeline.history), 1):
            lines.append(f"<b>{i}. [{entry['ts']}]</b> {entry['text']}")
            lines.append(f"   \u21b3 {entry['snippet']}\n")

        await update.message.reply_text('\n'.join(lines), parse_mode='HTML')

    # ------------------------------------------------------------------ messages

    async def handle_message(update: Update, _ctx):
        """Route any plain text message through the query pipeline."""
        reply = await asyncio.to_thread(pipeline.answer, update.message.text or '')
        # Use HTML parse mode whenever the reply contains HTML tags
        parse_mode = 'HTML' if any(tag in reply for tag in ('<pre>', '<b>', '<code>')) else None
        await update.message.reply_text(reply, parse_mode=parse_mode)

    # ------------------------------------------------------------------ startup

    app = ApplicationBuilder().token(pipeline.cfg.telegram_token).build()
    app.add_handler(CommandHandler('start',   cmd_start))
    app.add_handler(CommandHandler('help',    cmd_help))
    app.add_handler(CommandHandler('status',  cmd_status))
    app.add_handler(CommandHandler('history', cmd_history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info('Telegram bot starting (mock=%s)', pipeline.cfg.mock_mode)
    app.run_polling()


def main():
    cfg = Config.load()
    pipeline = QueryPipeline(cfg)

    if '--demo' in sys.argv:
        run_demo(pipeline)
        return

    if not cfg.telegram_token:
        log.warning('No Telegram token found — running in demo mode')
        run_demo(pipeline)
        return

    run_telegram(pipeline)


if __name__ == '__main__':
    main()
