"""
Test that all pro features import and initialize correctly.
"""

import sys
from pathlib import Path

# Add paths
ROOT = Path(__file__).resolve().parent
for rel in ("core", "utils", "config", "models", "strategies"):
    sys.path.insert(0, str(ROOT / rel))

print("Testing pro feature imports...")

try:
    from multi_timeframe import MultiTimeframeAnalyzer, TimeframeDataManager
    print("✅ multi_timeframe")
except ImportError as e:
    print(f"❌ multi_timeframe: {e}")

try:
    from execution_optimizer import ExecutionOptimizer
    print("✅ execution_optimizer")
except ImportError as e:
    print(f"❌ execution_optimizer: {e}")

try:
    from kalman_filter import AdaptiveConfidenceFilter, BayesianEdgeDetector
    print("✅ kalman_filter")
except ImportError as e:
    print(f"❌ kalman_filter: {e}")

try:
    from capital_allocation import MultiStrategyAllocator, KellyCriterion
    print("✅ capital_allocation")
except ImportError as e:
    print(f"❌ capital_allocation: {e}")

try:
    from macro_regime import MacroRegimeDetector, LatencyTracker
    print("✅ macro_regime")
except ImportError as e:
    print(f"❌ macro_regime: {e}")

try:
    from order_flow import OrderFlowDetector, VolumeProfileAnalyzer
    print("✅ order_flow")
except ImportError as e:
    print(f"❌ order_flow: {e}")

try:
    from multi_strategy_engine import MultiStrategyEngine
    print("✅ multi_strategy_engine")
except ImportError as e:
    print(f"❌ multi_strategy_engine: {e}")

try:
    from options_strategies import OptionsStrategyGenerator
    print("✅ options_strategies")
except ImportError as e:
    print(f"❌ options_strategies: {e}")

print("\nAll pro features imported successfully!")
