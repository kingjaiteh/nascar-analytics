from __future__ import annotations
import json
from data import get_connection


def query_race_data(sql: str) -> dict:
    try:
        con = get_connection()
        df = con.execute(sql).fetchdf()
        return {
            "success": True,
            "columns": list(df.columns),
            "row_count": len(df),
            "data": df.head(50).to_dict(orient="records"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def web_search(query: str) -> dict:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        return {"success": True, "results": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


def build_chart(data: list, chart_type: str, title: str, x: str, y: str, color: str | None = None) -> dict:
    return {"data": data, "chart_type": chart_type, "title": title, "x": x, "y": y, "color": color}


TOOL_DISPATCH = {
    "query_race_data": lambda inp: query_race_data(inp["sql"]),
    "web_search": lambda inp: web_search(inp["query"]),
    "build_chart": lambda inp: build_chart(**inp),
}
