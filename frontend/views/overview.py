import streamlit as st

from backend import service
from frontend import cached
from frontend.labels import inr, pct

headline = cached.headline()

st.title("Business overview")
st.write(
    f"Twelve months of sales for {headline['products']} products, "
    f"{headline['first_date']} to {headline['last_date']}."
)

columns = st.columns(4)
columns[0].metric("Revenue", inr(headline["revenue"]))
columns[1].metric("Units sold", f"{headline['units']:,}")
columns[2].metric("Gross margin", pct(headline["gross_margin_pct"]))
columns[3].metric("Units sold on promotion", pct(headline["promo_share_pct"]))

st.subheader("Needs attention")
attention = service.attention_summary()
counts = attention["status_counts"]
alerts = st.columns(3)
alerts[0].metric("Products at risk of running out", counts.get("stockout_risk", 0))
alerts[1].metric("Overstocked products", counts.get("overstock", 0))
alerts[2].metric(
    "Promotions that raised daily profit", pct(attention["profitable_promo_share_pct"])
)
if attention["stockout_risk"]:
    names = ", ".join(
        f"{item['name']} ({item['days_of_cover']} days left)" for item in attention["stockout_risk"]
    )
    st.warning(f"Running out before restock: {names}.")
st.caption("Open Explore analyses for the full detail behind each figure.")

st.subheader("Revenue by month and category")
st.bar_chart(cached.monthly_revenue(), y_label="Revenue (₹ lakh)", x_label="Month")

st.subheader("Categories")
st.dataframe(
    cached.category_summary(),
    hide_index=True,
    width="stretch",
    column_config={
        "Revenue (lakh)": st.column_config.NumberColumn(format="%.1f"),
        "Gross margin %": st.column_config.NumberColumn(format="%.1f"),
        "Average price": st.column_config.NumberColumn(format="%,.0f"),
    },
)

st.subheader("Busiest days of the week")
st.bar_chart(cached.weekday_demand(), y_label="Average units per product per day", sort=False)
