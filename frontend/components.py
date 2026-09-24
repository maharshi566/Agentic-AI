from collections.abc import Callable
from typing import Any

import pandas as pd
import streamlit as st

from frontend.labels import describe_scope, inr, pct, signed_pct

Columns = dict[str, tuple[str, str | None]]

SKU = ("SKU", None)
PRODUCT = ("Product", None)

STATUS_LABELS = {
    "healthy": "Healthy",
    "stockout_risk": "Stockout risk",
    "overstock": "Overstocked",
    "no_recent_demand": "No recent demand",
}


def show_table(title: str, rows: list[dict[str, Any]], columns: Columns) -> None:
    if not rows:
        return
    st.markdown(f"**{title}**")
    frame = pd.DataFrame(rows)[list(columns)].rename(
        columns={key: label for key, (label, _) in columns.items()}
    )
    config = {
        label: st.column_config.NumberColumn(label, format=number_format)
        for label, number_format in columns.values()
        if number_format
    }
    for label, number_format in columns.values():
        if not number_format:
            frame[label] = frame[label].fillna("-")
    st.dataframe(frame, hide_index=True, width="stretch", column_config=config)


def _window_caption(label: str, window: dict[str, Any]) -> None:
    st.caption(f"{label} · {window['start']} to {window['end']} ({window['days']} days)")


def _sales(output: dict[str, Any]) -> None:
    _window_caption(describe_scope(output["scope"]), output["window"])
    revenue_change = output["revenue_change_pct_vs_previous_period"]
    columns = st.columns(4)
    columns[0].metric("Revenue", inr(output["revenue"]), signed_pct(revenue_change))
    columns[1].metric(
        "Units sold",
        f"{output['units']:,}",
        signed_pct(output["units_change_pct_vs_previous_period"]),
    )
    columns[2].metric("Units per day", f"{output['avg_daily_units']:,.1f}")
    columns[3].metric("Sold on promotion", pct(output["promo_units_share_pct"]))
    if revenue_change is None:
        st.caption(
            "Growth is not shown because the previous period is not fully covered by history."
        )

    ranking: Columns = {
        "sku": SKU,
        "name": PRODUCT,
        "revenue": ("Revenue (₹)", "%,.0f"),
        "units": ("Units", "%,d"),
    }
    show_table("Best sellers", output["top_skus"], ranking)
    show_table("Weakest sellers", output["bottom_skus"], ranking)


def _inventory(output: dict[str, Any]) -> None:
    st.caption(
        f"{describe_scope(output['scope'])} · stock as of {output['as_of']}, "
        f"demand over the last {output['demand_window_days']} days"
    )
    counts = output["status_counts"]
    columns = st.columns(len(STATUS_LABELS))
    for column, (status, label) in zip(columns, STATUS_LABELS.items(), strict=True):
        column.metric(label, counts.get(status, 0))

    stock: Columns = {
        "sku": SKU,
        "name": PRODUCT,
        "on_hand": ("On hand", "%,d"),
        "avg_daily_units": ("Units per day", "%.1f"),
        "days_of_cover": ("Days of cover", "%.1f"),
        "lead_time_days": ("Supplier lead time (days)", "%,d"),
    }
    if "items" in output:
        show_table("Products", output["items"], {**stock, "status": ("Status", None)})
        return
    show_table("Products likely to run out before restocking", output["stockout_risk"], stock)
    show_table("Overstocked products", output["overstock"], stock)


def _pricing(output: dict[str, Any]) -> None:
    st.caption(f"{describe_scope(output['scope'])} · prices as of {output['as_of']}")
    columns = st.columns(4)
    columns[0].metric("Average margin", pct(output["avg_margin_pct"]))
    columns[1].metric("Lowest margin", pct(output["min_margin_pct"]))
    columns[2].metric("Highest margin", pct(output["max_margin_pct"]))
    columns[3].metric("Repriced in last 90 days", output["repriced_last_90_days"])

    show_table(
        "Lowest-margin products",
        output["lowest_margin_skus"],
        {
            "sku": SKU,
            "name": PRODUCT,
            "price": ("Price (₹)", "%,.0f"),
            "unit_cost": ("Unit cost (₹)", "%.2f"),
            "margin_pct": ("Margin %", "%.1f"),
            "last_change_date": ("Last price change", None),
            "last_change_pct": ("Change %", "%.1f"),
        },
    )
    if "price_history" in output:
        history = pd.DataFrame(output["price_history"]).set_index("effective_date")
        st.markdown("**Price history**")
        st.line_chart(history["price"], y_label="Price (₹)", x_label="Effective from")


def _assortment(output: dict[str, Any]) -> None:
    _window_caption(f"{output['category']} ({output['sku_count']} products)", output["window"])
    columns = st.columns(4)
    columns[0].metric("Category revenue", inr(output["category_revenue"]))
    columns[1].metric("Gross profit", inr(output["category_gross_profit"]))
    columns[2].metric("Gross margin", pct(output["gross_margin_pct"]))
    columns[3].metric("Products", output["sku_count"])

    classes = pd.DataFrame(
        {
            "Class": ["A (core)", "B (support)", "C (long tail)"],
            "Products": [output["class_summary"][c]["sku_count"] for c in "ABC"],
            "Share of revenue %": [output["class_summary"][c]["revenue_share_pct"] for c in "ABC"],
        }
    )
    st.markdown("**How revenue is concentrated**")
    st.dataframe(classes, hide_index=True, width="stretch")

    performance: Columns = {
        "sku": SKU,
        "name": PRODUCT,
        "abc_class": ("Class", None),
        "revenue_share_pct": ("Revenue share %", "%.1f"),
        "gross_profit": ("Gross profit (₹)", "%,.0f"),
        "units_per_day": ("Units per day", "%.1f"),
    }
    show_table("Top products", output["top_skus"], performance)
    show_table("Long-tail products with the lowest profit", output["tail_skus"], performance)
    if output["zero_sales_skus"]:
        st.warning("No sales in this period: " + ", ".join(output["zero_sales_skus"]))


def _promotions(output: dict[str, Any]) -> None:
    st.caption(f"{describe_scope(output['scope'])} · all completed promotions")
    if output["promotion_count"] == 0:
        st.info("No completed promotions with enough history to measure.")
        return
    columns = st.columns(4)
    columns[0].metric("Promotions measured", output["promotion_count"])
    columns[1].metric("Average discount", pct(output["avg_discount_pct"]))
    columns[2].metric("Average unit uplift", pct(output["avg_unit_uplift_pct"]))
    columns[3].metric("Increased daily profit", pct(output["profitable_promo_share_pct"]))

    promos: Columns = {
        "sku": SKU,
        "name": PRODUCT,
        "start_date": ("Start", None),
        "end_date": ("End", None),
        "discount_pct": ("Discount %", "%,.0f"),
        "unit_uplift_pct": ("Unit uplift %", "%.1f"),
        "daily_profit_change_pct": ("Daily profit change %", "%.1f"),
    }
    show_table("Most profitable promotions", output["most_profitable"], promos)
    show_table("Least profitable promotions", output["least_profitable"], promos)
    show_table("Most recent promotions", output["most_recent"], promos)


def _market(output: dict[str, Any]) -> None:
    st.caption(f"{describe_scope(output['scope'])} · market data source: {output['source']}")
    demand = output["category_demand"]
    if len(demand) == 1:
        columns = st.columns(2)
        columns[0].metric("Demand trend (30 days)", signed_pct(demand[0]["trend_pct_30d"]))
        columns[1].metric("Search interest (0-100)", demand[0]["search_interest_index"])
    else:
        show_table(
            "Demand by category",
            demand,
            {
                "category": ("Category", None),
                "trend_pct_30d": ("Demand trend, 30 days %", "%+.1f"),
                "search_interest_index": ("Search interest (0-100)", "%d"),
            },
        )

    position = output["price_position"]
    positions = pd.DataFrame(
        {
            "Products": [
                position["above_market"],
                position["at_parity"],
                position["below_market"],
            ]
        },
        index=["Above market", "At parity", "Below market"],
    )
    st.markdown("**Our prices against competitors**")
    st.bar_chart(positions, y_label="Products", horizontal=True, height=200)

    index: Columns = {
        "sku": SKU,
        "name": PRODUCT,
        "our_price": ("Our price (₹)", "%,.0f"),
        "competitor_avg_price": ("Competitor average (₹)", "%.2f"),
        "competitor_min_price": ("Competitor lowest (₹)", "%.2f"),
        "price_index": ("Price index (100 = parity)", "%.1f"),
    }
    show_table("Priced highest against the market", output["highest_price_index"], index)
    show_table("Priced lowest against the market", output["lowest_price_index"], index)


RENDERERS: dict[str, Callable[[dict[str, Any]], None]] = {
    "sales_summary": _sales,
    "inventory_status": _inventory,
    "pricing_info": _pricing,
    "assortment_analysis": _assortment,
    "promotion_history": _promotions,
    "market_signals": _market,
}


def render_output(tool: str, output: dict[str, Any]) -> None:
    RENDERERS[tool](output)
