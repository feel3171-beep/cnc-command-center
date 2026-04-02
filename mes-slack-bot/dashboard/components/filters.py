"""공통 필터 컴포넌트"""
import streamlit as st
from datetime import datetime, timedelta
import db
import config


def date_filter(key="date"):
    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("시작일", value=datetime.now() - timedelta(days=7), key=f"{key}_start")
    with col2:
        end = st.date_input("종료일", value=datetime.now(), key=f"{key}_end")
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def factory_filter(key="factory"):
    options = ["전체"] + list(config.FACTORY_NAMES.values())
    codes = ["ALL"] + list(config.FACTORY_NAMES.keys())
    selected = st.selectbox("공장", options, key=key)
    idx = options.index(selected)
    return codes[idx]


def get_factory_condition(factory_code, alias="o"):
    if factory_code == "ALL":
        return ""
    return f" AND {alias}.FACTORY_CODE = '{factory_code}'"
