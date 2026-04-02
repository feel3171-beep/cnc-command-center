"""공통 차트 컴포넌트"""
import plotly.express as px
import plotly.graph_objects as go


def gauge_chart(value, title, max_val=100, color_ranges=None):
    if color_ranges is None:
        color_ranges = [
            {"range": [0, 50], "color": "#ff4444"},
            {"range": [50, 80], "color": "#ffaa00"},
            {"range": [80, 100], "color": "#00cc66"},
        ]
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=value,
        title={"text": title},
        number={"suffix": "%"},
        gauge={
            "axis": {"range": [0, max_val]},
            "bar": {"color": "#2E75B6"},
            "steps": color_ranges,
        },
    ))
    fig.update_layout(height=250, margin=dict(t=50, b=20, l=20, r=20))
    return fig


def bar_chart(df, x, y, title, color=None, horizontal=False):
    if horizontal:
        fig = px.bar(df, y=x, x=y, title=title, color=color, orientation='h')
    else:
        fig = px.bar(df, x=x, y=y, title=title, color=color)
    fig.update_layout(height=400, margin=dict(t=50, b=40, l=40, r=20))
    return fig


def line_chart(df, x, y, title, color=None):
    fig = px.line(df, x=x, y=y, title=title, color=color, markers=True)
    fig.update_layout(height=400, margin=dict(t=50, b=40, l=40, r=20))
    return fig


def pie_chart(df, names, values, title):
    fig = px.pie(df, names=names, values=values, title=title)
    fig.update_layout(height=350, margin=dict(t=50, b=20, l=20, r=20))
    return fig


def metric_card_color(value, target):
    if value >= target:
        return "normal"
    return "inverse"
