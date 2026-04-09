#!/usr/bin/env python3
"""Regenerate and resend the training graph from existing training_report.json."""

from __future__ import annotations

import json
from pathlib import Path

from discord_alerts import discord
try:
    from train_stock_rf import SymbolTrainingResult, render_training_svg, render_training_png, HAS_PIL
except ImportError:
    from models.train_stock_rf import SymbolTrainingResult, render_training_svg, render_training_png, HAS_PIL


def main() -> int:
    report_json = Path("training_report.json")
    if not report_json.exists():
        print("training_report.json not found")
        return 1

    summary = json.loads(report_json.read_text(encoding="utf-8"))
    results = [SymbolTrainingResult(**item) for item in summary.get("results", [])]
    if not results:
        print("No symbol results in training_report.json")
        return 1

    svg_path = render_training_svg(results, summary, "training_report.svg")
    report_path = svg_path
    report_filename = "training_report.svg"
    if HAS_PIL:
        png_path = render_training_png(results, summary, "training_report.png")
        report_path = png_path
        report_filename = "training_report.png"
        print(f"Regenerated {png_path}")
    else:
        print(f"Regenerated {svg_path}")

    if discord.enabled:
        sent = discord.send_file(
            "Stock RF Training Report (Legend Updated)",
            {
                "Symbols": ", ".join(summary.get("symbols", [])),
                "Accuracy": f"{summary.get('overall_accuracy', 0.0):.3f}",
                "F1": f"{summary.get('overall_f1', 0.0):.3f}",
                "AUC": f"{summary.get('overall_auc', 0.0):.3f}",
            },
            report_path,
            filename=report_filename,
        )
        print(f"Discord report sent: {sent}")
    else:
        print("Discord disabled")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())