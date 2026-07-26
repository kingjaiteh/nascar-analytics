from __future__ import annotations
import os
import duckdb

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TRANSFORMED = os.path.join(_BASE, "cup_series_transformed")

_VIEWS = {
    "cup": os.path.join(_TRANSFORMED, "cup_series_transformed.csv"),
    "xfinity": os.path.join(_BASE, "xfinity_series_data.csv"),
    "truck": os.path.join(_BASE, "truck_series_data.csv"),
    "driver_stats": os.path.join(_TRANSFORMED, "driver_table", "driver_season_stats.csv"),
    "team_stats": os.path.join(_TRANSFORMED, "team_table", "team_season_stats.csv"),
    "track_stats": os.path.join(_TRANSFORMED, "track_table", "team_season_stats.csv"),
    "manuf_stats": os.path.join(_TRANSFORMED, "manuf_table", "manuf_season_stats.csv"),
}

_con: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    global _con
    if _con is not None:
        return _con
    _con = duckdb.connect()
    for view_name, path in _VIEWS.items():
        _con.execute(
            f"CREATE VIEW {view_name} AS SELECT * FROM read_csv_auto('{path}', header=true)"
        )
    return _con
