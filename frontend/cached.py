import pandas as pd
import streamlit as st

from backend import service

CATEGORY_COLUMNS = {
    "category": "Category",
    "products": "Products",
    "revenue_lakh": "Revenue (lakh)",
    "gross_margin_pct": "Gross margin %",
    "average_price": "Average price",
    "promotions": "Promotions",
}


@st.cache_data(show_spinner=False)
def _headline(signature: tuple[str, int]) -> dict:
    return service.headline()


@st.cache_data(show_spinner=False)
def _monthly_revenue(signature: tuple[str, int]) -> pd.DataFrame:
    frame = pd.DataFrame(service.revenue_by_month())
    return frame.pivot(index="month", columns="category", values="revenue_lakh")


@st.cache_data(show_spinner=False)
def _weekday_demand(signature: tuple[str, int]) -> pd.DataFrame:
    return pd.DataFrame(service.weekday_demand()).set_index("day")


@st.cache_data(show_spinner=False)
def _category_summary(signature: tuple[str, int]) -> pd.DataFrame:
    frame = pd.DataFrame(service.category_summary())
    return frame[list(CATEGORY_COLUMNS)].rename(columns=CATEGORY_COLUMNS)


def headline() -> dict:
    return _headline(service.data_signature())


def monthly_revenue() -> pd.DataFrame:
    return _monthly_revenue(service.data_signature())


def weekday_demand() -> pd.DataFrame:
    return _weekday_demand(service.data_signature())


def category_summary() -> pd.DataFrame:
    return _category_summary(service.data_signature())
