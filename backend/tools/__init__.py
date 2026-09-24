from langchain_core.tools import BaseTool

from backend.tools.assortment_tool import assortment_analysis
from backend.tools.inventory_tool import inventory_status
from backend.tools.market_tool import market_signals
from backend.tools.pricing_tool import pricing_info
from backend.tools.promotion_tool import promotion_history
from backend.tools.sales_tool import sales_summary

TOOLS: dict[str, BaseTool] = {
    t.name: t
    for t in (
        sales_summary,
        inventory_status,
        pricing_info,
        assortment_analysis,
        promotion_history,
        market_signals,
    )
}
