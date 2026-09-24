from typing import Any

TOOL_LABELS = {
    "sales_summary": "Sales performance",
    "inventory_status": "Stock position",
    "pricing_info": "Pricing and margins",
    "assortment_analysis": "Range analysis",
    "promotion_history": "Promotion results",
    "market_signals": "Market and competitors",
}

TOOL_QUESTIONS = {
    "sales_summary": "How are sales trending, and which products lead or lag?",
    "inventory_status": "Which products might run out, and which are overstocked?",
    "pricing_info": "What are current prices and margins, and what changed recently?",
    "assortment_analysis": "Which products drive the category, and which are the long tail?",
    "promotion_history": "Did past promotions lift sales and protect profit?",
    "market_signals": "How do our prices compare with competitors, and is demand rising?",
}

LAKH = 1e5
CRORE = 1e7


def inr(value: float) -> str:
    if abs(value) >= CRORE:
        return f"₹{value / CRORE:.2f} crore"
    if abs(value) >= LAKH:
        return f"₹{value / LAKH:.1f} lakh"
    return f"₹{value:,.0f}"


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}%"


def signed_pct(value: float | None) -> str | None:
    return None if value is None else f"{value:+.1f}%"


def describe_scope(scope: dict[str, Any]) -> str:
    if scope["sku"]:
        return f"{scope['sku']} ({scope['category']})"
    if scope["category"]:
        return f"{scope['category']} ({scope['sku_count']} products)"
    return f"Whole store ({scope['sku_count']} products)"


def describe_arguments(args: dict[str, Any]) -> str:
    parts = [args.get("sku") or args.get("category") or "Whole store"]
    if "days" in args:
        parts.append(f"last {args['days']} days")
    return " · ".join(parts)
