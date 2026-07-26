# NASCAR Analytics

A data pipeline over 75 years of NASCAR race results, with an AI agent on top that answers questions in plain English by writing and running SQL.

```
Question -> LLM agent -> SQL over DuckDB -> answer + chart
```

The agent does not answer from memory. Every number in every response comes from a query it wrote and ran against the data at request time.

## The pipeline

Race results start as `.rda` files in the [`nascaR.data`](https://github.com/kyleGrealis/nascaR.data) R package, which scrapes DriverAverages.com weekly.

1. **Extract.** `converter.py` and `convert_all.py` read the `.rda` files with `pyreadr` and write one CSV per series.
2. **Transform.** `Dimentions_transformed.ipynb` runs PySpark locally over the Cup results. It adds derived columns the raw data does not have (`Track_Type`, `Car_Generation`, `Percent_Laps_Led`, `Pos_Gained-Loss`, `Lead_Lap`, `Top_5`, `Top_10`) and builds four season-level aggregate tables.
3. **Serve.** `data.py` registers every CSV as a DuckDB view in memory. No database server, no load step.

| Table | Grain | Coverage |
|---|---|---|
| `cup` | one row per driver per race | 1949 to present, ~100,000 rows |
| `xfinity` | one row per driver per race | 1982 to present, ~60,000 rows |
| `truck` | one row per driver per race | 1995 to present, ~30,000 rows |
| `driver_stats` | season x driver | races, wins, top 5, top 10, avg finish, win rate |
| `team_stats` | season x team | same shape as driver stats |
| `track_stats` | season x track | field size, avg finish, race counts |
| `manuf_stats` | season x manufacturer | entries, wins, win rate per entry |

The CSVs are committed, so everything runs on a fresh clone with no setup.

## The agent layer

`agent.py` is a hand written tool-use loop, not a framework, so the control flow stays visible:

1. Send the conversation and the tool definitions to the model.
2. If the reply contains tool calls, run them and append the results.
3. Repeat until the model answers without calling a tool. Capped at 12 turns.

Three tools are available to it:

| Tool | What it does |
|---|---|
| `query_race_data` | Runs SQL against DuckDB and returns up to 50 rows |
| `web_search` | Looks up anything outside the dataset, like a result from last weekend |
| `build_chart` | Returns a Plotly spec that the UI renders after the turn finishes |

A few decisions worth calling out:

**The tool description carries the schema.** `query_race_data`'s description spells out every table and column, including the ones that need quoting in SQL (`"Seg Points"`, `"Pos_Gained-Loss"`). The model writes SQL straight against that. There is no text-to-SQL layer and no schema retrieval step.

**The system prompt forbids answering from memory.** A model's training data on a driver's 2015 road course record is often stale or wrong, so the prompt requires a query before any factual claim.

**Tool errors go back to the model, not up the stack.** A bad column name or malformed JSON arguments come back as a tool result, so the model gets a chance to fix its own query.

**The loop is provider agnostic.** Conversation state lives in a neutral format and `providers.py` translates it into each vendor's wire format on the way out. Providers can also stash their native response for verbatim replay, which Anthropic needs so thinking blocks survive a tool round trip.

## Running it

```bash
git clone https://github.com/kingjaiteh/nascar-analytics.git
cd nascar-analytics/Main_Project/chatbot
pip install -r requirements.txt
streamlit run app.py
```

Pick a provider in the sidebar and paste the matching API key. Keys are used for that session only and never written to disk. If the provider's env var is already set, the field pre-fills.

| Provider | Models | Key from |
|---|---|---|
| Anthropic | Claude Opus, Sonnet, Haiku | [console.anthropic.com](https://console.anthropic.com) |
| OpenRouter | Llama, Qwen, DeepSeek, Mistral | [openrouter.ai/keys](https://openrouter.ai/keys) |
| Groq | Llama 3.3, Qwen 3, Kimi K2 | [console.groq.com/keys](https://console.groq.com/keys) |
| Together AI | Llama, Qwen, DeepSeek V3 | [api.together.ai](https://api.together.ai/settings/api-keys) |
| Ollama | anything pulled locally | no key, runs offline |

Any model ID a provider serves can be typed into the custom model box, so new releases work without a code change.

Tool calling is the one hard requirement. Small models that do not reliably emit tool calls will answer without querying, which defeats the point. 70B class and up works well.

Questions it handles:

- Who has the most all-time Cup wins?
- Best road course drivers since 2015
- Compare Hendrick vs Joe Gibbs Racing wins by decade
- Which manufacturer dominates superspeedways?

## Refreshing the data

```bash
# 1. Fetch the upstream R package, which is not vendored here
git clone https://github.com/kyleGrealis/nascaR.data Main_Project/nascaR.data

# 2. .rda to CSV
cd Main_Project
pip install pyreadr
python converter.py      # cup
python convert_all.py    # xfinity and truck

# 3. Rebuild the aggregate tables
#    Run cup_series_transformed/Dimentions_transformed.ipynb
```

## Layout

```
Main_Project/
  converter.py, convert_all.py      extract step
  cup_series_transformed/
    Dimentions_transformed.ipynb    PySpark transform
    *.csv, */                       transformed and aggregate tables
  *_series_data.csv                 raw series exports
  chatbot/
    app.py                          Streamlit UI
    agent.py                        tool-use loop and tool definitions
    providers.py                    provider adapters
    tools.py                        tool implementations
    data.py                         DuckDB views
    deploy.ps1, ec2_setup.sh        deploy behind nginx on EC2
```

`deploy.ps1` and `ec2_setup.sh` are configured through `NASCAR_EC2_HOST`, `NASCAR_EC2_KEY` and `NASCAR_APP_DIR`. No host or key details are committed.

## Notes

Race data is derived from `nascaR.data` by Kyle Grealis, MIT licensed. The code in this repository is available under the same terms.
