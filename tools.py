"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    
    listings = load_listings()

    # Hard filters — applied before scoring
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    if size is not None:
        size_lower = size.lower()
        listings = [l for l in listings if size_lower in l["size"].lower()]

    # Build a set of lowercase tokens from the description
    query_tokens = set(description.lower().split())

    # Score each listing by counting token overlap with title words + tag words
    scored = []
    for listing in listings:
        title_tokens = set(listing["title"].lower().split())
        # Each style_tag may be multi-word ("graphic tee") — split each into words
        tag_tokens = {
            word
            for tag in listing["style_tags"]
            for word in tag.lower().split()
        }
        score = len(query_tokens & (title_tokens | tag_tokens))
        if score > 0:
            scored.append((score, listing))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [listing for _, listing in scored[:5]]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    """
    client = _get_groq_client()
    items = wardrobe.get("items", [])

    if not items:
        prompt = (
            f"You are a thrift fashion stylist. A user just found this secondhand item:\n\n"
            f"Item: {new_item['title']}\n"
            f"Category: {new_item['category']}\n"
            f"Colors: {', '.join(new_item.get('colors', []))}\n"
            f"Style tags: {', '.join(new_item.get('style_tags', []))}\n\n"
            f"They don't have a wardrobe on file yet. Give 2-3 sentences of general styling advice: "
            f"what kinds of bottoms, shoes, or accessories pair well with this piece, and what overall vibe to aim for. "
            f"End with one actionable styling tip (a tuck, a roll, or a layering idea). "
            f"Write in second person, conversational and specific — not generic."
        )
    else:
        # Score each wardrobe item by tag + color overlap with the new item
        item_tags = set(new_item.get("style_tags", []))
        item_colors = set(new_item.get("colors", []))

        scored = []
        for w_item in items:
            tag_overlap = len(set(w_item.get("style_tags", [])) & item_tags)
            color_overlap = len(set(w_item.get("colors", [])) & item_colors)
            scored.append((tag_overlap + color_overlap, w_item))

        # Sort descending; stable sort preserves original order on ties (best-effort)
        scored.sort(key=lambda x: x[0], reverse=True)
        top_picks = [w_item for _, w_item in scored[:3]]

        wardrobe_lines = []
        for w in top_picks:
            notes_str = f" ({w['notes']})" if w.get("notes") else ""
            wardrobe_lines.append(
                f"- {w['name']} [{w['category']}]"
                f" — colors: {', '.join(w['colors'])}"
                f"; tags: {', '.join(w['style_tags'])}"
                f"{notes_str}"
            )

        prompt = (
            f"You are a thrift fashion stylist. A user just found this secondhand item:\n\n"
            f"New item: {new_item['title']}\n"
            f"Category: {new_item['category']}\n"
            f"Colors: {', '.join(new_item.get('colors', []))}\n"
            f"Style tags: {', '.join(new_item.get('style_tags', []))}\n\n"
            f"Their wardrobe (most relevant pieces):\n"
            + "\n".join(wardrobe_lines) +
            f"\n\nWrite a 2-3 sentence outfit suggestion using these wardrobe pieces. "
            f"Sentence 1: name the best bottom or outerwear from the list by its exact name "
            f"and briefly explain the style connection to the new item. "
            f"Sentence 2: name the best shoe or accessory from the list by its exact name. "
            f"Sentence 3: give one actionable styling tip — a tuck, a roll, a layering note, "
            f"or a color pairing rationale. "
            f"Use second person ('your [piece name]'). Be specific, not generic."
        )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    """
    # Normalize: treat empty/whitespace the same as None
    outfit_clean = (outfit or "").strip() or None
    title = new_item.get("title") if new_item else None

    # Both completely missing: hardcoded fallback
    if not title and not outfit_clean:
        return "Check out my latest thrift find — styling details coming soon."

    # Build item context — only include fields that are present
    item_lines = []
    if title:
        item_lines.append(f"Item: {title}")
    price = new_item.get("price")
    if price is not None:
        item_lines.append(f"Price: ${price:.0f}")
    platform = new_item.get("platform")
    if platform:
        item_lines.append(f"Platform: {platform.lower()}")
    if new_item.get("brand"):
        item_lines.append(f"Brand: {new_item['brand']}")
    if new_item.get("condition"):
        item_lines.append(f"Condition: {new_item['condition']}")

    # Tell the LLM which fields to include or skip
    field_instructions = []
    if price is not None:
        field_instructions.append(f"mention the price as ${price:.0f}")
    else:
        field_instructions.append("omit the price (not available)")
    if platform:
        field_instructions.append(f"mention the platform as '{platform.lower()}'")
    else:
        field_instructions.append("omit the platform (not available)")

    # Outfit section varies by whether a suggestion exists
    if outfit_clean:
        outfit_section = (
            f"Outfit suggestion:\n{outfit_clean}\n\n"
            f"Reference one specific wardrobe pairing or styling detail from the outfit suggestion."
        )
    else:
        outfit_section = (
            "No outfit suggestion available. "
            "Instead of a wardrobe pairing, write 'and the styling possibilities are endless'."
        )

    prompt = (
        f"You are writing a casual, first-person Instagram/TikTok caption for a thrift find.\n\n"
        f"{chr(10).join(item_lines)}\n\n"
        f"{outfit_section}\n\n"
        f"Write 1-2 sentences in a casual, authentic OOTD voice — not a product description. "
        f"{' and '.join(field_instructions).capitalize()}. "
        f"End with a short hook like 'full look in my stories' or 'link in bio'. "
        f"Output only the caption — no quotes, no explanation."
    )

    client = _get_groq_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        max_tokens=120,
    )
    return response.choices[0].message.content.strip()
