import logging, sys, time
from config import Config
from query_parser import QueryParser
from sheets_handler import SheetsHandler
from validator import validate

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger('bot')

class QueryPipeline:
    def __init__(self, cfg):
        self.cfg = cfg
        self.sheets = SheetsHandler(cfg.google_sheet_id, cfg.google_credentials_path, cfg.sheet_range, cfg.cache_ttl_seconds, cfg.mock_mode)
        self.parser = QueryParser(cfg.openai_api_key, cfg.openai_model, cfg.mock_mode)

    def answer(self, user_text):
        t0 = time.time()
        columns, dtypes = self.sheets.schema()
        try:
            parsed = self.parser.parse(user_text, columns)
        except Exception as e:
            return f'Parse error: {e}'
        result = validate(parsed, columns, dtypes)
        if not result.ok:
            return 'Query error:\n' + '\n'.join(f'- {e}' for e in result.errors)
        try:
            output = self.sheets.execute(result.normalized_query)
        except Exception as e:
            return f'Execution error: {e}'
        log.info('query completed in %.2fs', time.time() - t0)
        return _format(output)

def _format(output):
    a = output.get('action')
    if a == 'count': return f"Count: {output['value']} row(s) match."
    if a in ('sum','avg','min','max'):
        v = output.get('value')
        if v is None: return f'No data for {a}.'
        label = {'sum':'Total','avg':'Average','min':'Minimum','max':'Maximum'}[a]
        return f"{label} {output.get('target_column','')}: {v:,.2f} (from {output.get('row_count',0)} row(s))"
    if a == 'list':
        rows = output.get('rows',[])
        if not rows: return 'No rows match those filters.'
        hdr = list(rows[0].keys())
        lines = [' | '.join(hdr), '-'*40]
        for r in rows[:20]: lines.append(' | '.join(str(r.get(h,'')) for h in hdr))
        suffix = '' if len(rows)<=20 else f'\n... and {len(rows)-20} more'
        return 'Matched ' + str(len(rows)) + ' row(s):\n' + '\n'.join(lines) + suffix
    return str(output)

def run_demo(pipeline):
    for q in [
        'List customers in Phase 2 with Payment_Percent more than 60',
        'How many customers are in Phase 1?',
        'Total Amount where Phase is 2',
        'Average Payment_Percent where Phase is 2',
        'Show customers in Region East',
        'List customers where Status is Paused',
        'Max Amount where Phase is 3',
    ]:
        print(f'Q: {q}\n{pipeline.answer(q)}\n' + '-'*60)

def run_telegram(pipeline):
    import asyncio
    from telegram import Update
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

    async def start(update, _ctx):
        cols, _ = pipeline.sheets.schema()
        await update.message.reply_text(f'Hi! Ask me about the sheet.\nColumns: {", ".join(cols)}')

    async def handle(update, _ctx):
        reply = await asyncio.to_thread(pipeline.answer, update.message.text or '')
        await update.message.reply_text(reply)

    app = ApplicationBuilder().token(pipeline.cfg.telegram_token).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    log.info('Telegram bot starting (mock=%s)', pipeline.cfg.mock_mode)
    app.run_polling()

def main():
    cfg = Config.load(); pipeline = QueryPipeline(cfg)
    if '--demo' in sys.argv: run_demo(pipeline); return
    if not cfg.telegram_token: log.warning('No token — demo mode'); run_demo(pipeline); return
    run_telegram(pipeline)

if __name__ == '__main__': main()
