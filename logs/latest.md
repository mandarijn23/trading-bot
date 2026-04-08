# Trading Bot Report - Wed Apr  8 08:29:56 AM UTC 2026

## Service Status
● trading-bot-stock.service - Trading Bot Stock Paper Session (NAS)
     Loaded: loaded (/etc/systemd/system/trading-bot-stock.service; disabled; preset: enabled)
     Active: active (running) since Wed 2026-04-08 08:27:16 UTC; 2min 39s ago
TriggeredBy: ● trading-bot-stock.timer
   Main PID: 160506 (python)
      Tasks: 23 (limit: 19019)
     Memory: 121.8M (peak: 122.0M)
        CPU: 2.985s
     CGroup: /system.slice/trading-bot-stock.service
             └─160506 /home/nas/trading-bot/.venv/bin/python stock_bot.py

## Recent Logs
Apr 08 08:20:06 nas run_stock_session.sh[156589]: Traceback (most recent call last):
Apr 08 08:20:06 nas run_stock_session.sh[156589]:   File "/home/nas/trading-bot/stock_bot.py", line 560, in <module>
Apr 08 08:20:06 nas run_stock_session.sh[156589]:     logging.error(f"Failed to start bot: {e}")
Apr 08 08:20:06 nas run_stock_session.sh[156589]: ^^^^^^
Apr 08 08:20:06 nas run_stock_session.sh[156589]:   File "/home/nas/trading-bot/stock_bot.py", line 551, in main
Apr 08 08:20:06 nas run_stock_session.sh[156589]:     
Apr 08 08:20:06 nas run_stock_session.sh[156589]:   File "/home/nas/trading-bot/stock_bot.py", line 476, in run
Apr 08 08:20:06 nas run_stock_session.sh[156589]:     """Main trading loop."""
Apr 08 08:20:06 nas run_stock_session.sh[156589]:     ^^^^^^^^^^^^^^^^^^^^^^^
Apr 08 08:20:06 nas run_stock_session.sh[156589]:   File "/home/nas/trading-bot/stock_bot.py", line 405, in _wait_until_open
Apr 08 08:20:06 nas run_stock_session.sh[156589]:     def _wait_until_open(self) -> None:
Apr 08 08:20:06 nas run_stock_session.sh[156589]:             ^^^^^^^^^^^^^^^^^^^^^^^^^
Apr 08 08:20:06 nas run_stock_session.sh[156589]: KeyboardInterrupt
Apr 08 08:20:06 nas systemd[1]: Stopping trading-bot-stock.service - Trading Bot Stock Paper Session (NAS)...
Apr 08 08:20:07 nas systemd[1]: trading-bot-stock.service: Deactivated successfully.
Apr 08 08:20:07 nas systemd[1]: Stopped trading-bot-stock.service - Trading Bot Stock Paper Session (NAS).
Apr 08 08:20:07 nas systemd[1]: trading-bot-stock.service: Consumed 3.227s CPU time, 1.1M memory peak, 0B memory swap peak.
Apr 08 08:20:07 nas systemd[1]: Started trading-bot-stock.service - Trading Bot Stock Paper Session (NAS).
Apr 08 08:20:07 nas systemd[1]: trading-bot-stock.service: Main process exited, code=exited, status=203/EXEC
Apr 08 08:20:07 nas systemd[1]: trading-bot-stock.service: Failed with result 'exit-code'.
Apr 08 08:24:27 nas systemd[1]: Started trading-bot-stock.service - Trading Bot Stock Paper Session (NAS).
Apr 08 08:24:27 nas systemd[1]: trading-bot-stock.service: Main process exited, code=exited, status=203/EXEC
Apr 08 08:24:27 nas systemd[1]: trading-bot-stock.service: Failed with result 'exit-code'.
Apr 08 08:27:16 nas systemd[1]: Started trading-bot-stock.service - Trading Bot Stock Paper Session (NAS).
Apr 08 08:27:17 nas run_stock_session.sh[160506]: ✅ Discord notifications enabled
Apr 08 08:27:17 nas run_stock_session.sh[160506]: ✅ Random Forest model initialized
Apr 08 08:27:17 nas run_stock_session.sh[160506]: 2026-04-08 08:27:17  INFO     ? Connected to Alpaca (PAPER TRADING)
Apr 08 08:27:17 nas run_stock_session.sh[160506]: 2026-04-08 08:27:17  INFO     ? Stock Bot started | Symbols: ['SPY', 'QQQ', 'VOO'] | 15Min
Apr 08 08:27:17 nas run_stock_session.sh[160506]: 2026-04-08 08:27:17  INFO     ? AI active | Trades: 0 | WR: 0%
Apr 08 08:27:17 nas run_stock_session.sh[160506]: 2026-04-08 08:27:17  INFO     Market closed | opens in 303 minutes

## Code Quality
- ML Model: ✅ GOOD
- Lock State: ✅ GOOD

## Memory Usage
nas       160506  1.8  1.1 1292508 183188 ?      Ssl  08:27   0:02 /home/nas/trading-bot/.venv/bin/python stock_bot.py
