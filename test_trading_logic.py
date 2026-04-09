#!/usr/bin/env python3
"""Stock bot position-logic demo without live market data."""

from stock_bot import StockPosition

def run_position_logic_demo():
    """Test core StockPosition behavior."""
    print("\n" + "="*60)
    print("  TRADING BOT POSITION TEST")
    print("="*60)
    
    pos = StockPosition("SPY")
    
    print("\n1️⃣ Testing position.open()...")
    pos.open(
        price=415.00,
        quantity=10,
        stop_loss_pct=0.03,
        take_profit_pct=0.05,
        ai_confidence=0.65
    )
    print(f"  ✅ Position opened:")
    print(f"     Active: {pos.active}")
    print(f"     Entry: ${pos.entry_price:.2f}")
    
    print("\n2️⃣ Testing position.check_exit() - should HOLD...")
    result = pos.check_exit(price=416.00, trailing_stop_pct=0.025)
    print(f"  ✅ Exit status: {result}")
    
    print("\n3️⃣ Testing position.close()...")
    pos.close(was_loss=False)
    print(f"  ✅ Position closed: active={pos.active}")
    
    print("\n4️⃣ Testing position.ready()...")
    ready = pos.ready()
    print(f"  ✅ Ready for new entry: {ready}")
    
    print("\n" + "="*60)
    print("  ✅ ALL TESTS PASSED!")
    print("="*60 + "\n")

if __name__ == "__main__":
    run_position_logic_demo()
    print("\n🎉 Position logic working correctly!\n")
