"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        # parsed parameters (flat keys, per planning.md State Management)
        "description": None,         # parsed style keywords
        "size": None,                # parsed size filter (str or None)
        "max_price": None,           # parsed price ceiling (float or None)
        # tool outputs
        "search_results": [],        # full list returned by search_listings
        "selected_item": None,       # results[0]; read by suggest_outfit + create_fit_card
        "wardrobe": wardrobe,        # wardrobe dict with "items" list
        "outfit_text": None,         # string returned by suggest_outfit; None if skipped
        "fit_card": None,            # string returned by create_fit_card
        # control flags
        "search_failed": False,      # True if search_listings returned []
        "error": None,               # human-readable message when interaction ended early
    }


# ── query parser ──────────────────────────────────────────────────────────────

# Price patterns: "under $30", "$30", "30 dollars", "max 30", "up to $30"
_PRICE_PAT = re.compile(
    r'(?:under|below|less\s+than|max|up\s+to|no\s+more\s+than)\s*\$?(\d+(?:\.\d+)?)'
    r'|\$(\d+(?:\.\d+)?)'
    r'|(\d+(?:\.\d+)?)\s*(?:dollars|bucks)',
    re.IGNORECASE,
)

# Size patterns:
#   "size M" / "size XL" / "size W30 L30"  — with explicit "size" prefix
#   "W30", "W28 L30"                        — waist sizes are unambiguous
#   "XXS", "XS", "XL", "XXL", "XXXL"       — distinctive enough without prefix
#   Plain "S", "M", "L" are not matched without "size" prefix — too ambiguous
_SIZE_PAT = re.compile(
    r'\bsize\s+(xxs|xs|s/m|s|m|l|xl|xxl|xxxl|w\d{2}(?:\s*l\d{2})?)'
    r'|\b(w\d{2}(?:\s*l\d{2})?)\b'
    r'|\b(xxs|xs|xl|xxl|xxxl)\b',
    re.IGNORECASE,
)


def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a free-text query using regex.
    Returns a dict with keys: description (str), size (str|None), max_price (float|None).
    """
    price_match = _PRICE_PAT.search(query)
    max_price = None
    if price_match:
        raw = next(g for g in price_match.groups() if g is not None)
        max_price = float(raw)

    size_match = _SIZE_PAT.search(query)
    size = None
    if size_match:
        size = next(g for g in size_match.groups() if g is not None).upper()

    # Description: remove price and size tokens, collapse leftover whitespace/punctuation
    cleaned = _PRICE_PAT.sub("", query)
    cleaned = _SIZE_PAT.sub("", cleaned)
    description = re.sub(r"[,.\s]+", " ", cleaned).strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse query → write flat keys directly onto session
    parsed = _parse_query(query)
    session["description"] = parsed["description"]
    session["size"] = parsed["size"]
    session["max_price"] = parsed["max_price"]

    if not session["description"]:
        session["error"] = (
            "Please describe what you're looking for "
            "(e.g., 'vintage graphic tee, size M, under $30')."
        )
        return session

    # Step 3: Search — exit early if nothing matches
    results = search_listings(
        session["description"], size=session["size"], max_price=session["max_price"]
    )
    session["search_results"] = results

    if not results:
        session["search_failed"] = True
        parts = [f"No listings found for '{session['description']}'"]
        if session["max_price"] is not None:
            parts.append(f"under ${session['max_price']:.0f}")
        if session["size"] is not None:
            parts.append(f"in size {session['size']}")
        session["error"] = (
            " ".join(parts)
            + ". Try a broader keyword, a higher price, or a different size."
        )
        return session

    # Step 4: Select top result
    session["selected_item"] = results[0]

    # Step 5: Outfit suggestion — skip entirely if wardrobe is empty
    if not wardrobe.get("items"):
        session["outfit_text"] = None
    else:
        session["outfit_text"] = suggest_outfit(session["selected_item"], wardrobe)

    # Step 6: Fit card (handles outfit_text=None internally)
    session["fit_card"] = create_fit_card(
        session["outfit_text"], session["selected_item"]
    )

    # Step 7: Return completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_text']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
