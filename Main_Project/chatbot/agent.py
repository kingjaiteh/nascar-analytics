from __future__ import annotations
from tools import TOOL_DISPATCH
from providers import LLMProvider

# Guard against a model that keeps calling tools without ever answering.
MAX_TURNS = 12

TOOL_DEFINITIONS = [
    {
        "name": "query_race_data",
        "description": (
            "Execute SQL against the NASCAR database. Available tables:\n"
            "- cup: Cup Series 1949–present. Columns: Season, Race, Track, Name, Length, Surface, "
            "Finish, Start, Car, Driver, Make, Pts, Laps, Led, Status, Team, S1, S2, Rating, Win, "
            '"Seg Points", Percent_Laps_Led, Race_ID, Lead_Lap, Track_Type, Car_Generation, '
            '"Pos_Gained-Loss", Did_Finish, Top_5, Top_10. '
            "Track_Type values: 'intermediate', 'road course', 'short', 'speedway', 'superspeedway'.\n"
            "- xfinity: Xfinity Series 1982–present (Season, Race, Track, Name, Length, Surface, "
            "Finish, Start, Car, Driver, Make, Pts, Laps, Led, Status, Team, S1, S2, Rating, Win, "
            '"Seg Points").\n'
            "- truck: Truck Series 1995–present (same schema as xfinity).\n"
            "- driver_stats: Cup season-level driver aggregates (Season, Driver, Races, Top5, Top10, "
            "Wins, Avg_Finish, Total_Points, Total_Laps, Total_Laps_Led, Lead_Lap_Finishes, "
            "Avg_Start, Best_Finish, Worst_Finish, Win_Pct, Laps_Led_Pct).\n"
            "- team_stats: Same structure as driver_stats but grouped by Team.\n"
            "- track_stats: (Season, Track, Track_Type, Total_Entries, Races_At_Track, Avg_Laps, "
            "Lead_Lap_Finishers, Different_Winners).\n"
            "- manuf_stats: (Season, Make, Entries, Wins, Top5, Top10, Avg_Finish, Win_Rate_Per_entry).\n\n"
            'Important: quote column names with spaces or hyphens: "Seg Points", "Pos_Gained-Loss". '
            "Return at most 50 rows unless more are requested."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SQL query to run against the NASCAR database."}
            },
            "required": ["sql"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the web for current NASCAR news, live standings, recent race results, "
            "or driver/team info not covered by the historical database."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "build_chart",
        "description": (
            "Queue a Plotly chart for rendering in the dashboard. Always call this after "
            "query_race_data when showing rankings, trends, or comparisons."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "array", "description": "Array of row objects to plot."},
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "line", "scatter", "pie"],
                    "description": "Plotly chart type.",
                },
                "title": {"type": "string"},
                "x": {"type": "string", "description": "Column name for x-axis (or pie labels)."},
                "y": {"type": "string", "description": "Column name for y-axis (or pie values)."},
                "color": {
                    "type": "string",
                    "description": "Optional column name to use for color grouping.",
                },
            },
            "required": ["data", "chart_type", "title", "x", "y"],
        },
    },
]

_SERIES_CONTEXT = {
    "Cup":    "The user is focused on the Cup Series. Default to the `cup` table unless told otherwise.",
    "Xfinity": "The user is focused on the Xfinity Series. Default to the `xfinity` table unless told otherwise.",
    "Truck":  "The user is focused on the Truck Series. Default to the `truck` table unless told otherwise.",
}

_TOOL_LABELS = {
    "query_race_data": "Querying database...",
    "web_search":      "Searching the web...",
    "build_chart":     "Building chart...",
}

BASE_SYSTEM_PROMPT = """You are a NASCAR analytics assistant with access to historical race data:
- Cup Series: 1949–present (100,000+ race entries), data is current through the 2026 season
- Xfinity Series: 1982–present
- Truck Series: 1995–present

Guidelines:
1. ALWAYS query the database for any specific stat, win, finish, or season fact — never rely on your training knowledge for these. Your training data may be wrong or outdated; the database is the source of truth.
2. For questions about a specific driver at a specific track, always run a SQL query filtering by both Driver and Track before stating any fact.
3. Call build_chart whenever showing rankings, trends, or comparisons — the dashboard will render it automatically.
4. Be specific: cite numbers, seasons, win rates. Don't hedge when the data is clear.
5. Track_Type in the cup table uses: 'intermediate', 'road course', 'short', 'speedway', 'superspeedway'. Indianapolis Motor Speedway appears as both 'Indianapolis Motor Speedway' (oval) and 'Indianapolis Motor Speedway Road Course' depending on the year — query both when relevant.
6. Quote column names with spaces or hyphens in SQL: "Seg Points", "Pos_Gained-Loss"."""


def run_agent(
    messages: list,
    provider: LLMProvider,
    active_series: str = "Cup",
    on_tool_call=None,
) -> tuple[str, list]:
    """
    Run the tool-use loop against any provider.

    `messages` is the neutral history described in providers.py; it is mutated in
    place with each assistant turn and tool-result batch, so the caller keeps the
    full conversation. Returns (final_text, charts).
    """
    charts: list[dict] = []
    system_prompt = (
        BASE_SYSTEM_PROMPT
        + "\n\nActive series context: "
        + _SERIES_CONTEXT.get(active_series, "")
    )

    for _ in range(MAX_TURNS):
        turn = provider.chat(system_prompt, messages, TOOL_DEFINITIONS)

        messages.append({
            "role": "assistant",
            "content": turn.text,
            "tool_calls": turn.tool_calls,
            "raw": turn.raw,
            "raw_provider": turn.raw_provider,
        })

        if turn.stop_reason == "refusal":
            return (
                "That request was declined. Try rephrasing it as a question about "
                "NASCAR race data.",
                charts,
            )

        if not turn.tool_calls:
            note = ""
            if turn.stop_reason in ("max_tokens", "length"):
                note = "\n\n_(Response was cut off at the token limit.)_"
            return turn.text + note, charts

        results = []
        for call in turn.tool_calls:
            if on_tool_call:
                on_tool_call(_TOOL_LABELS.get(call.name, call.name))

            tool_fn = TOOL_DISPATCH.get(call.name)
            if tool_fn is None:
                output = {"success": False, "error": f"Unknown tool: {call.name}"}
            else:
                try:
                    output = tool_fn(call.arguments)
                except Exception as e:
                    # Return the failure to the model so it can correct itself,
                    # rather than aborting the whole turn.
                    output = {"success": False, "error": f"{type(e).__name__}: {e}"}

                if call.name == "build_chart" and isinstance(output, dict) and "chart_type" in output:
                    charts.append(output)
                    output = {"success": True, "message": "Chart queued for rendering."}

            results.append({"id": call.id, "name": call.name, "output": output})

        messages.append({"role": "tool_results", "results": results})

    return (
        "Stopped after too many tool calls without a final answer. "
        "Try a more specific question, or a more capable model.",
        charts,
    )
