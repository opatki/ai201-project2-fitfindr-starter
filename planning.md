# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Loads all listings from `listings.json` via `load_listings()`, filters by `size` and `max_price` if provided, scores each remaining listing by keyword overlap between `description` and the listing's `title` + `style_tags`, and returns the top matches sorted highest-score-first.

**Input parameters:**
- `description` (str): Free-text style description (e.g., `"vintage graphic tee"`). Used to match against each listing's `title` and `style_tags` fields by splitting into lowercase tokens and counting overlapping words.
- `size` (str, optional): Target size string (e.g., `"M"`, `"W30"`). Filters to listings where `listing["size"]` contains this value (case-insensitive). If omitted or `None`, no size filter is applied.
- `max_price` (float, optional): Maximum acceptable price. Filters to listings where `listing["price"] <= max_price`. If omitted or `None`, no price filter is applied.

**What it returns:**
A list of up to 5 listing dicts sorted by descending relevance score (most keyword matches first). Each dict is the full listing record with all fields intact: `id` (str), `title` (str), `description` (str), `category` (str — one of tops/bottoms/outerwear/shoes/accessories), `style_tags` (list of str), `size` (str), `condition` (str — excellent/good/fair), `price` (float), `colors` (list of str), `brand` (str or None), `platform` (str — depop/thredUp/poshmark). Returns an empty list `[]` if no listing passes the filters or scores above zero.

**What happens if it fails or returns nothing:**
The planning loop checks `len(results) == 0` immediately after the call. If true, it sets `session["search_failed"] = True`, composes the message `"No listings found for '[description]' under $[max_price] in size [size]. Try a broader keyword, a higher price ceiling, or a different size."`, returns that message to the user, and exits — `suggest_outfit` and `create_fit_card` are never called.

---

### Tool 2: suggest_outfit

**What it does:**
Scores each wardrobe item against the new listing by counting shared entries between the item's `style_tags`/`colors` and the listing's `style_tags`/`colors`, selects the top 2–3 wardrobe pieces with the highest overlap, and returns a natural-language outfit recommendation that names those pieces by their `name` field and includes one concrete styling tip.

**Input parameters:**
- `new_item` (dict): A single listing dict as returned by `search_listings` — must have at minimum `title` (str), `style_tags` (list of str), `colors` (list of str), and `category` (str). Used as the anchor piece to build the outfit around.
- `wardrobe` (dict): A wardrobe dict with an `"items"` key containing a list of wardrobe item dicts. Each item has `id` (str), `name` (str), `category` (str), `colors` (list of str), `style_tags` (list of str), and optional `notes` (str or None). Loaded via `get_example_wardrobe()` from `data_loader.py`.

**What it returns:**
A plain string of 2–3 sentences. Sentence 1 names the top matching bottom or outerwear by its `name` field and explains the style connection (e.g., shared tags or complementary colors). Sentence 2 names the top matching shoe or accessory. Sentence 3 gives one actionable styling tip — a tuck, a roll, a layering note, or a color pairing rationale. Example: `"Pair this with your baggy straight-leg jeans and chunky white sneakers for a relaxed streetwear look. Add the black crossbody bag to keep it effortless. Roll the sleeves once to break up the silhouette."`

**What happens if it fails or returns nothing:**
The planning loop checks `len(session["wardrobe"]["items"]) == 0` before calling this tool. If the wardrobe is empty, `suggest_outfit` is skipped entirely, `session["outfit_text"]` is set to `None`, and `create_fit_card` is called with `outfit=None` — the fit card then uses generic styling language instead of named wardrobe pieces. If the wardrobe is non-empty but no item shares any tag or color with `new_item`, the tool still returns a best-effort suggestion using the closest categorical match (e.g., any bottom if the new item is a top).

---

### Tool 3: create_fit_card

**What it does:**
Formats the outfit suggestion and the purchased listing's metadata into a short, first-person social media caption written in the voice of someone who just thrifted the piece — referencing the platform, price, and at least one specific wardrobe pairing pulled from the outfit text.

**Input parameters:**
- `outfit` (str or None): The outfit suggestion string returned by `suggest_outfit`. If `None` (wardrobe was empty), the caption is generated from the item alone using generic styling language.
- `new_item` (dict): The listing dict selected in Step 1. Must have `title` (str), `price` (float), and `platform` (str) to build the caption. `brand` (str or None) and `condition` (str) are used if present to add detail.

**What it returns:**
A single string of 1–2 sentences — a first-person caption. It mentions the platform (lowercase, e.g., `"depop"`), the price formatted as `$XX`, references one key wardrobe pairing or styling detail from `outfit` (the first piece named), and ends with a short hook such as `"full look in my stories"` or `"link in bio"`. Example: `"thrifted this faded graphic tee off depop for $24 and it was made for my baggy jeans 🖤 full look in my stories"`

**What happens if it fails or returns nothing:**
If `new_item` is missing `price` or `platform`, those fields are omitted from the caption and the item `title` is used in their place. If `outfit` is `None`, the wardrobe-pairing reference is replaced with a generic phrase like `"and the styling possibilities are endless"`. If both `outfit` is `None` and `new_item` is missing `title`, the tool returns the hardcoded fallback string: `"Check out my latest thrift find — styling details coming soon."`

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop runs once per user message. It does not re-prompt or retry — it either completes all three tools in sequence or exits early on a failed step.

```
1. Parse the user message for three signals:
   - description (str): required — any style/item keywords (e.g., "vintage graphic tee")
   - size (str or None): optional — look for patterns like "size M", "M", "W30"
   - max_price (float or None): optional — look for patterns like "under $30", "$30", "30 dollars"
   If description is missing or empty, return:
     "Please describe what you're looking for (e.g., 'vintage graphic tee, size M, under $30')."
   and stop.

2. Call search_listings(description, size, max_price).
   Check: if len(results) == 0:
     → set session["search_failed"] = True
     → return "No listings found for '[description]'[optionally: under $[max_price]][optionally: in size [size]].
               Try a broader keyword, a higher price, or a different size."
     → STOP. Do not call suggest_outfit or create_fit_card.
   Else:
     → set session["selected_item"] = results[0]
     → proceed to step 3.

3. Check: if len(session["wardrobe"]["items"]) == 0:
     → set session["outfit_text"] = None
     → skip suggest_outfit entirely, proceed to step 4.
   Else:
     → call suggest_outfit(new_item=session["selected_item"], wardrobe=session["wardrobe"])
     → set session["outfit_text"] = result (the suggestion string)
     → proceed to step 4.

4. Call create_fit_card(outfit=session["outfit_text"], new_item=session["selected_item"]).
   → set session["fit_card"] = result (the caption string)
   → proceed to step 5.

5. Compose and return the final response to the user:
   - Line 1: listing title, price, platform, condition
     (e.g., "Found: Graphic Tee — 2003 Tour Bootleg Style — $24, Depop, good condition")
   - Line 2: outfit suggestion (session["outfit_text"]) — omit this block if None
   - Line 3: fit card caption (session["fit_card"])
   The agent is done.
```

---

## State Management

**How does information from one tool get passed to the next?**

The agent initializes a `session` dict at the start of each user request. Each tool call reads its inputs from `session` and writes its output back into `session` before the next tool is invoked. The planning loop reads `session` keys to decide what to call next and whether to short-circuit.

```python
session = {
    "query": str,           # the original user message
    "description": str,     # parsed style keywords
    "size": str | None,     # parsed size filter
    "max_price": float | None,  # parsed price ceiling
    "wardrobe": dict,       # wardrobe dict with "items" list; default get_example_wardrobe()
    "selected_item": dict | None,   # results[0] from search_listings; None until set
    "outfit_text": str | None,      # suggestion string from suggest_outfit; None if skipped
    "fit_card": str | None,         # caption string from create_fit_card; None until set
    "search_failed": bool,  # True if search_listings returned []
}
```

Flow:
- `search_listings` writes `session["selected_item"]` (or sets `session["search_failed"] = True`).
- `suggest_outfit` reads `session["selected_item"]` and `session["wardrobe"]`; writes `session["outfit_text"]`.
- `create_fit_card` reads `session["outfit_text"]` and `session["selected_item"]`; writes `session["fit_card"]`.
- The final response reads `session["selected_item"]`, `session["outfit_text"]`, and `session["fit_card"]`.

The `session` dict is local to one call of `run_agent()` and is not persisted between user messages.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | `results == []` — no listing passes the size/price filters or scores above zero | Set `session["search_failed"] = True`. Return: `"No listings found for '[description]'[under $X][in size Y]. Try a broader keyword, a higher price, or a different size."` Stop — do not call tools 2 or 3. |
| suggest_outfit | `session["wardrobe"]["items"] == []` — user has no wardrobe items | Skip `suggest_outfit` entirely. Set `session["outfit_text"] = None`. Proceed to `create_fit_card`, which generates a caption from the item alone using generic styling language. |
| create_fit_card | `new_item` missing `price` or `platform`; or `outfit` is `None` | Omit the missing fields from the caption. If `outfit` is `None`, replace the wardrobe-pairing reference with `"and the styling possibilities are endless"`. If both `outfit` is `None` and `new_item` has no `title`, return hardcoded fallback: `"Check out my latest thrift find — styling details coming soon."` |

---

## Architecture

```
User message
     │
     ▼
┌──────────────────────────────────────────────────────────┐
│                     Planning Loop                        │
│  Parse description, size, max_price from user message    │
│  Initialize session dict; set session["wardrobe"]        │
│  If description is empty → ask for clarification, stop   │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
              search_listings(description, size, max_price)
              [reads: listings.json via load_listings()]
                           │
               ┌───────────┴────────────┐
          results == []            results >= 1
               │                        │
               ▼                        ▼
      "No listings found..."   session["selected_item"] = results[0]
       → return to user                 │
       → STOP                           ▼
                         suggest_outfit(new_item, wardrobe)
                         [reads: session["selected_item"],
                                 session["wardrobe"]]
                                        │
                          ┌─────────────┴─────────────┐
                    wardrobe empty              wardrobe non-empty
                          │                           │
                          ▼                           ▼
              session["outfit_text"] = None   session["outfit_text"]
                          │                    = suggestion string
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                         create_fit_card(outfit, new_item)
                         [reads: session["outfit_text"],
                                 session["selected_item"]]
                                        │
                                        ▼
                         session["fit_card"] = caption string
                                        │
                                        ▼
                         Return final response to user:
                           • listing title, price, platform, condition
                           • outfit suggestion (omitted if None)
                           • fit card caption
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

- **search_listings**: Give Claude the Tool 1 spec from this file (all four fields) plus the listing field list from `data_loader.py`. Ask it to implement `search_listings(description, size=None, max_price=None)` using `load_listings()`, scoring by lowercase token overlap between `description` and each listing's `title` + `style_tags`, filtering by `size` (substring match) and `max_price` (≤), and returning the top 5 sorted by score descending. Verify with three manual queries: (1) `"vintage graphic tee"` — expect lst_006 in results; (2) `"vintage graphic tee", max_price=10.0` — expect empty list; (3) `"flannel", size="XL"` — expect lst_003.

- **suggest_outfit**: Give Claude the Tool 2 spec from this file plus `wardrobe_schema.json`. Ask it to implement `suggest_outfit(new_item, wardrobe)` that scores each wardrobe item by counting shared entries between the item's `style_tags`/`colors` and the listing's, picks the top 2–3 pieces, and returns a 2–3 sentence string naming pieces by their `name` field. Verify by calling it with lst_006 (graphic tee) and the example wardrobe — confirm the output names real pieces like "baggy straight-leg jeans" or "chunky white sneakers" and ends with a styling tip.

- **create_fit_card**: Give Claude the Tool 3 spec from this file plus one example listing dict and one example outfit string. Ask it to implement `create_fit_card(outfit, new_item)` that produces a 1–2 sentence first-person caption using `new_item["platform"]`, `new_item["price"]`, and the first wardrobe piece named in `outfit`. Verify that the output contains the correct platform and price, reads naturally in first person, and hits the fallback correctly when called with `outfit=None` and a minimal `new_item`.

**Milestone 4 — Planning loop and state management:**

Give Claude the Planning Loop and State Management sections from this file plus the Architecture diagram. Ask it to implement `run_agent(user_message, wardrobe=None)` that: initializes the `session` dict as specified, parses `description`/`size`/`max_price` from `user_message`, and executes the exact conditional chain from the Planning Loop section. Verify end-to-end with four test cases: (1) full happy path — "vintage graphic tee under $30" with the example wardrobe; (2) no-results path — "cashmere overcoat under $5" — confirm tools 2 and 3 are never called; (3) empty wardrobe path — valid query but `get_empty_wardrobe()` — confirm `suggest_outfit` is skipped and a caption is still returned; (4) missing description — bare message "something nice" with no parseable keywords — confirm the agent asks for clarification and stops.

---

## A Complete Interaction (Step by Step)

FitFindr is a thrift shopping assistant that takes a user's style request, searches `listings.json` for matching secondhand items using `search_listings`, then passes the best result to `suggest_outfit` to build a look using the user's existing wardrobe, and finally calls `create_fit_card` to generate a shareable caption. Each tool depends on the output of the previous one — `suggest_outfit` receives the top listing and the wardrobe dict loaded via `get_example_wardrobe()`, and `create_fit_card` receives the outfit text and that same listing. If `search_listings` returns nothing, the agent tells the user what to adjust (broader keywords, higher budget, different size) and stops — it never calls downstream tools with empty or missing input.

---

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent calls `search_listings("vintage graphic tee", max_price=30.0)`. It scans `listings.json` for items whose `style_tags` include "vintage" or "graphic tee", whose `price` is ≤ 30.0, and ranks them by relevance. Two listings match: `lst_002` (Y2K Baby Tee, $18, S/M, Depop, excellent) and `lst_006` (Graphic Tee — 2003 Tour Bootleg Style, $24, L, Depop, good). The tool returns both sorted by relevance; the agent picks the top result: **lst_006 — "Graphic Tee — 2003 Tour Bootleg Style, $24, Depop, good condition."**

**Step 2:**
The agent calls `suggest_outfit(new_item=lst_006, wardrobe=get_example_wardrobe())`. The wardrobe includes baggy straight-leg jeans (w_001), chunky white sneakers (w_007), and a black crossbody bag (w_010). The tool matches the tee's `style_tags` ("vintage", "streetwear") against the wardrobe items and returns: **"Pair this faded graphic tee with your baggy straight-leg jeans and chunky white sneakers for a relaxed streetwear look. Let it hang untucked and loose — add the black crossbody bag to keep it effortless."**

**Step 3:**
The agent calls `create_fit_card(outfit=<suggestion from step 2>, new_item=lst_006)`. It formats the outfit and item details into a shareable social caption. Returns: **"thrifted this faded graphic tee off depop for $24 and it was made for my baggy jeans 🖤 full look in my stories"**

**Final output to user:**
The user sees the top matching listing (title, price, platform, condition), the outfit suggestion with specific styling notes referencing their actual wardrobe pieces, and the ready-to-post fit card caption.

**Error path:**
If `search_listings` returns an empty list — for example, no tops in size L match "vintage graphic tee" under $30 — the agent responds: "I couldn't find any vintage graphic tees in your size under $30 right now. Try searching with a higher budget (up to $40), a different size, or a broader term like 'band tee' or 'streetwear top'." The interaction ends there; `suggest_outfit` and `create_fit_card` are not called.
