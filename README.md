# FitFindr

FitFindr is a thrift shopping assistant that takes a natural language style request, searches a dataset of secondhand listings for matching items, suggests an outfit using the user's existing wardrobe, and generates a shareable social media caption for the find.

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Run the Gradio UI:

```bash
python app.py
```

Then open the localhost URL shown in your terminal (usually `http://localhost:7860`).

Run the tests:

```bash
python -m pytest tests/ -v
```

---

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe (10 items)
├── utils/
│   └── data_loader.py         # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tools.py                   # search_listings, suggest_outfit, create_fit_card
├── agent.py                   # run_agent() — the planning loop
├── app.py                     # Gradio UI
├── tests/
│   └── test_tools.py          # 25 pytest tests covering all three tools
└── planning.md                # Full design spec
```

---

## Tool Inventory

### Tool 1: `search_listings`

**Purpose:** Filters the mock listings dataset and ranks results by keyword relevance so the agent can pick the best match for the user's request.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Free-text style keywords (e.g., `"vintage graphic tee"`). Matched against listing `title` and `style_tags` by lowercase token overlap. |
| `size` | `str \| None` | Size filter (e.g., `"M"`, `"W30"`). Case-insensitive substring match against `listing["size"]`. Pass `None` to skip. |
| `max_price` | `float \| None` | Inclusive price ceiling. Filters to `listing["price"] <= max_price`. Pass `None` to skip. |

**Output:** A list of up to 5 listing dicts sorted by descending relevance score (most keyword matches first). Each dict contains all fields from `listings.json`: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Returns `[]` if nothing matches — never raises an exception.

---

### Tool 2: `suggest_outfit`

**Purpose:** Given a thrifted item and the user's wardrobe, selects the best matching wardrobe pieces and asks a Groq LLM to write a 2–3 sentence outfit recommendation that names those pieces explicitly.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `new_item` | `dict` | A listing dict from `search_listings`. Must have `title`, `style_tags`, `colors`, and `category`. Used as the anchor piece. |
| `wardrobe` | `dict` | A wardrobe dict with an `"items"` key. Each item has `id`, `name`, `category`, `colors`, `style_tags`, and optional `notes`. May be empty. |

**Output:** A non-empty string. If the wardrobe has items, a 2–3 sentence suggestion naming wardrobe pieces by their `name` field with one actionable styling tip (a tuck, a roll, a layering note). If the wardrobe is empty, 2–3 sentences of general styling advice for the item.

---

### Tool 3: `create_fit_card`

**Purpose:** Formats the outfit suggestion and listing metadata into a casual, first-person social media caption in the voice of someone who just thrifted the piece.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `outfit` | `str` | Outfit suggestion string from `suggest_outfit`. The function also accepts `None` at runtime (when the wardrobe is empty); it normalizes empty/whitespace values to `None` internally and generates generic styling language instead of named pieces. |
| `new_item` | `dict` | The listing dict from Step 1. Uses `title`, `price`, and `platform` to build the caption. |

**Output:** A 1–2 sentence first-person caption mentioning the platform (lowercase), price as `$XX`, a specific styling detail or wardrobe pairing, and a short hook (`"full look in my stories"`, `"link in bio"`).

---

## Planning Loop

The loop runs once per user message and either completes all three tools in sequence or exits early on a failed step. It never retries.

```
1. Parse query → extract description (required), size (optional), max_price (optional)
   using regex patterns. If description is empty after stripping, return a clarification
   prompt and stop.

2. Call search_listings(description, size, max_price).
   → If results == []: set search_failed=True, return an error message, STOP.
   → If results >= 1: set selected_item = results[0], continue.

3. Check wardrobe:
   → If wardrobe["items"] == []: set outfit_text = None, skip suggest_outfit.
   → If wardrobe has items: call suggest_outfit, set outfit_text = result.

4. Call create_fit_card(outfit_text, selected_item).
   → set fit_card = result.

5. Return the completed session dict. The UI reads selected_item, outfit_text,
   and fit_card to populate the three output panels.
```

The query parser uses two compiled regex patterns — one for price (`"under $30"`, `"$30"`, `"30 dollars"`) and one for size (`"size M"` with prefix for S/M/L; `"W30"` and `"XL/XXL/XXS"` without prefix because they are unambiguous). Parsed signals are stored as flat keys on the session dict (`session["description"]`, `session["size"]`, `session["max_price"]`).

---

## State Management

The agent initializes a `session` dict at the start of each `run_agent()` call. Every tool reads its inputs from `session` and writes its output back before the next tool is called. The dict is local to one call — nothing is persisted between messages.

```python
session = {
    "query": str,             # original user message
    "description": str,       # parsed style keywords
    "size": str | None,       # parsed size filter
    "max_price": float | None,# parsed price ceiling
    "search_results": list,   # all results from search_listings
    "selected_item": dict | None,   # results[0]; read by suggest_outfit + create_fit_card
    "wardrobe": dict,         # wardrobe passed in; read by suggest_outfit
    "outfit_text": str | None,      # from suggest_outfit; None if wardrobe was empty
    "fit_card": str | None,         # from create_fit_card
    "search_failed": bool,    # True if search_listings returned []
    "error": None | str,      # human-readable message if interaction ended early
}
```

Data flows strictly forward: `search_listings` → `selected_item`; `suggest_outfit` reads `selected_item` + `wardrobe`, writes `outfit_text`; `create_fit_card` reads `outfit_text` + `selected_item`, writes `fit_card`. No tool reads the output of a later tool.

---

## Error Handling

### `search_listings` — no results

**Failure mode:** No listing passes the size/price filters, or no listing scores above zero on keyword overlap.

**Agent response:** Sets `session["search_failed"] = True` and `session["error"]` to a message that includes the original description and whichever filters were active. Returns the session immediately — `suggest_outfit` and `create_fit_card` are never called.

**Concrete example from testing:**
```
Input:  search_listings("designer ballgown", size="XXS", max_price=5)
Output: []
Agent error: "No listings found for 'designer ballgown' under $5 in size XXS.
             Try a broader keyword, a higher price, or a different size."
```

### `suggest_outfit` — empty wardrobe

**Failure mode:** `wardrobe["items"]` is an empty list (new user with no wardrobe on file).

**Agent response:** Skips `suggest_outfit` entirely. Sets `session["outfit_text"] = None`. Proceeds to `create_fit_card`, which detects the `None` and generates a caption using generic styling language (`"and the styling possibilities are endless"`).

**Concrete example from testing:**
```
Input:  suggest_outfit skipped; create_fit_card(outfit=None, new_item=lst_002)
Output: "Just scored this adorable Y2K baby tee with a butterfly print on depop
         for $18 and the styling possibilities are endless, full look in my stories"
```

### `create_fit_card` — missing outfit and item

**Failure mode:** `outfit` is `None` or empty/whitespace AND `new_item` has no `title` field.

**Agent response:** Returns a hardcoded fallback string without making any LLM call.

**Concrete example from testing:**
```
Input:  create_fit_card(None, {})
Output: "Check out my latest thrift find — styling details coming soon."
```

---

## Spec Reflection

**One way the spec helped:** The error handling table in `planning.md` made a real gap visible before the code was even run. The first draft of `run_agent` set `session["error"]` on empty search results but never set `session["search_failed"]`. The table explicitly required both. Because the spec named every field and every mutation, the omission was caught during the conformance review rather than during debugging — no test failure needed to surface it.

**One way implementation diverged from the spec and why:** The spec listed `"description"`, `"size"`, and `"max_price"` as flat top-level session keys from the start, but the first generated implementation wrapped them in a nested `"parsed"` dict (`session["parsed"] = {"description": ..., "size": ..., "max_price": ...}`). It also used `"outfit_suggestion"` where the spec said `"outfit_text"`. These weren't logic errors — both structures store the same data — but they meant the code wasn't directly readable against the Architecture diagram. The divergence happened because the AI generated idiomatic Python (nested dict for grouped data, descriptive key name) rather than following the schema literally. The fix was mechanical: flatten the keys and rename the field everywhere it appeared. The lesson is that AI tools will produce reasonable-looking code that drifts from the spec on naming and structure unless the spec is quoted literally in the prompt.

---

## AI Usage

### Instance 1: Implementing `search_listings`

**Input to Claude:** The full Tool 1 section from `planning.md` (all four fields: what it does, input parameters with types, return value description, failure mode), plus the listing field list from `data_loader.py`'s docstring.

**Prompt intent:** "Implement `search_listings(description, size=None, max_price=None)` using `load_listings()` from `data_loader.py`. Score by lowercase token overlap between `description` and each listing's `title` + `style_tags`. Filter by `size` (case-insensitive substring) and `max_price` (≤). Return top 5 sorted by score descending, empty list on no match."

**What it produced:** A working implementation. The scoring used a set intersection on title words and split tag words, which matched the spec exactly. The size filter used `.lower() in listing["size"].lower()`, which handles `"m"` matching `"S/M"` correctly.

**What I verified and kept:** Ran three manual test cases before trusting it — `"vintage graphic tee"` (expected results), `max_price=10.0` (expected `[]`), `"flannel", size="XL"` (expected lst_003). All passed with no changes needed.

---

### Instance 2: Implementing `run_agent`

**Input to Claude:** The Planning Loop section, the State Management section (including the full session dict schema), and the Architecture ASCII diagram — all from `planning.md`.

**Prompt intent:** "Implement `run_agent(query, wardrobe)` following the five-step conditional chain in the Planning Loop section. Use regex to parse `description`, `size`, and `max_price` from the query. Initialize the session dict exactly as shown in State Management. Set `search_failed = True` on empty results. Skip `suggest_outfit` if `wardrobe['items']` is empty."

**What it produced:** A working implementation with a `_parse_query` helper using compiled regex patterns for price and size, and a clean sequential planning loop. The session was initialized with `"parsed"` as a nested dict (wrapping description/size/max_price) and used `"outfit_suggestion"` instead of `"outfit_text"`.

**What I changed before using it:** Two conformance fixes. First, the nested `"parsed"` dict was replaced with flat top-level keys (`session["description"]`, `session["size"]`, `session["max_price"]`) to match the State Management schema in planning.md. Second, `"outfit_suggestion"` was renamed to `"outfit_text"` everywhere — in `_new_session`, in `run_agent`, and in the CLI test — to match the Architecture diagram's label. The `"search_failed"` key was also missing from the initial session and had to be added. These changes made the code directly readable against the spec.
