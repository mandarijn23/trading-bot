# Trading Bot Master To-Do

Last updated: 2026-04-13

## Current Progress
- [x] Week 1: Execution reliability
- [x] Week 2: Persistence and observability
- [x] Week 2.5: Query CLI
- [ ] Week 3: Portfolio analytics
- [ ] Week 4: Operational hardening

## Priority Queue (Do These Next)
- [x] Build query CLI entry point in observability/query_cli.py
- [x] Add slippage analysis method in persistence/trade_record.py
- [x] Add symbol-plus-date filtering helper in persistence/trade_record.py
- [x] Add tests for query CLI outputs and argument handling
- [x] Add README usage examples for query CLI commands
- [x] Start Week 3 with portfolio heat and correlation circuit breaker
- [x] Add Week 3B sector exposure gate and imbalance alerts

## Week 2.5 - Query CLI (P0, 1 day)

### Scope
- [x] Create file observability/query_cli.py
- [x] Add cmd_daily: daily PnL summary by date
- [x] Add cmd_strategy: strategy stats (win rate, PF, avg win/loss)
- [x] Add cmd_slippage: slippage summary and variance
- [x] Add cmd_trades: list trades by symbol and optional since date
- [x] Add cmd_reconcile: backtest vs live variance summary

### Persistence Additions
- [x] Add get_slippage_analysis() in persistence/trade_record.py
- [x] Add get_trades_by_symbol(symbol, since=None) optional date filtering

### Tests and Docs
- [x] Add tests/test_query_cli.py
- [x] Manual check with real DB data on at least 3 commands
- [x] Update README with command examples

### Definition of Done
- [x] All query CLI commands return correct output against seeded test DB
- [x] Query CLI tests pass
- [x] Existing regression suite still passes

## Week 3 - Portfolio Analytics (P0, 3-4 days)

### Correlation and Heat
- [x] Create module for correlation matrix and portfolio heat
- [x] Add high-correlation alert threshold (> 0.85)
- [x] Add portfolio heat circuit breaker (> 15% blocks new entries)
- [x] Wire checks into stock bot pre-entry flow
- [x] Add tests for correlation math and heat breaker behavior

### Sector Exposure
- [x] Create sector mapping and exposure tracker
- [x] Add sector limit enforcement (example: tech <= 40%)
- [x] Add sector imbalance alert
- [x] Add tests for mapping and limit enforcement

### Benchmark and Tearsheet
- [x] Add benchmark tracker (SPY and VTI comparison)
- [x] Add monthly return vs benchmark summary
- [x] Add tearsheet generator (monthly report)
- [x] Add tests for benchmark calculations
- [x] Add tests for tearsheet report calculations

### Definition of Done
- [ ] Hourly correlation and heat stats produced
- [x] New entries blocked when heat exceeds threshold
- [ ] Monthly tearsheet generated without manual edits

## Week 4 - Operational Hardening (P1, 3-4 days)

### Health Monitoring
- [x] Create health monitor (API heartbeat, CPU, memory, disk)
- [x] Add Discord alerts on critical health failures
- [x] Add tests with failure injection

### Emergency Controls
- [ ] Create emergency controls (kill, pause, resume)
- [ ] Require confirmation token or guard for kill path
- [ ] Add tests for close-all and pause/resume flows

### Anomaly Detection
- [ ] Add trade-frequency anomaly detector
- [ ] Add sudden PnL deterioration detector
- [ ] Add liquidity and exchange-status anomaly checks
- [ ] Add tests for anomaly triggers

### Compliance and Tax
- [ ] Add wash sale detection
- [ ] Add FIFO cost basis tracking
- [ ] Add Form 8949 export data generator
- [ ] Add tests for tax math and detection logic

### Definition of Done
- [ ] Health failures detected and alerted in under 30 seconds
- [ ] Emergency close-all works in test harness
- [ ] Tax export generated from persisted trades

## Backlog (After Week 4)
- [ ] Hedge effectiveness monitoring
- [ ] Stress testing harness for extreme volatility scenarios
- [ ] Advanced execution (TWAP and VWAP)
- [ ] Strategy version pinning and rollback metadata
- [ ] Automated backups for DB and logs

## Session Checklist
Use this at the start of each work session.

- [ ] Pull latest master
- [ ] Pick one section from Priority Queue
- [ ] Implement code and tests together
- [ ] Run targeted tests plus key regressions
- [ ] Commit with clear scope
- [ ] Update this file: mark completed items and add any new blockers
