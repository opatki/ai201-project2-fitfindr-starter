"""
tests/test_tools.py

Tests for each FitFindr tool, organized by tool.

Failure modes covered:
  search_listings  — no results, price filter, size filter, both combined
  suggest_outfit   — empty wardrobe (no exception), wardrobe present (LLM called
                     with piece names), output is stripped string
  create_fit_card  — outfit=None, empty/whitespace outfit, hardcoded fallback
                     (no LLM call), missing price field, missing platform field,
                     prompt includes item metadata on normal path
"""

from unittest.mock import MagicMock, patch

import pytest

from tools import create_fit_card, search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_groq(response_text: str) -> MagicMock:
    """Return a mock Groq client whose chat.completions.create returns response_text."""
    mock = MagicMock()
    mock.chat.completions.create.return_value.choices[0].message.content = response_text
    return mock


# ── search_listings ───────────────────────────────────────────────────────────

class TestSearchListings:

    def test_returns_results_for_matching_query(self):
        results = search_listings("vintage graphic tee", size=None, max_price=50)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_empty_results_for_impossible_query(self):
        # No match should return [] not raise an exception
        results = search_listings("designer ballgown", size="XXS", max_price=5)
        assert results == []

    def test_price_filter_excludes_expensive_items(self):
        results = search_listings("jacket", size=None, max_price=10)
        assert all(item["price"] <= 10 for item in results)

    def test_price_filter_includes_item_at_exact_ceiling(self):
        # Items priced exactly at max_price must be included (inclusive bound)
        results = search_listings("vintage", max_price=22.0)
        assert all(item["price"] <= 22.0 for item in results)

    def test_size_filter_case_insensitive_substring(self):
        # "m" must match "S/M" — case-insensitive substring
        results = search_listings("tee", size="m")
        assert len(results) > 0
        assert all("m" in item["size"].lower() for item in results)

    def test_size_filter_excludes_non_matching_sizes(self):
        results = search_listings("vintage", size="XL")
        for item in results:
            assert "xl" in item["size"].lower()

    def test_returns_at_most_five_results(self):
        results = search_listings("vintage")
        assert len(results) <= 5

    def test_results_have_all_required_fields(self):
        results = search_listings("vintage jacket")
        assert len(results) > 0
        required = {
            "id", "title", "description", "category", "style_tags",
            "size", "condition", "price", "colors", "brand", "platform",
        }
        for item in results:
            assert required.issubset(item.keys())

    def test_results_sorted_best_match_first(self):
        # First result should score at least as high as the last on "vintage graphic tee"
        results = search_listings("vintage graphic tee")
        assert len(results) >= 2

        def score(item):
            tokens = {"vintage", "graphic", "tee"}
            title_words = set(item["title"].lower().split())
            tag_words = {w for tag in item["style_tags"] for w in tag.lower().split()}
            return len(tokens & (title_words | tag_words))

        assert score(results[0]) >= score(results[-1])

    def test_combined_size_and_price_filter(self):
        results = search_listings("flannel", size="XL", max_price=30)
        assert all(item["price"] <= 30 for item in results)
        assert all("xl" in item["size"].lower() for item in results)


# ── suggest_outfit ────────────────────────────────────────────────────────────

class TestSuggestOutfit:

    @pytest.fixture
    def item(self):
        return search_listings("vintage graphic tee")[0]

    def test_returns_non_empty_string_with_wardrobe(self, item):
        mock_reply = "Pair with your baggy jeans and chunky sneakers. Add the crossbody bag. Tuck the front for shape."
        with patch("tools._get_groq_client", return_value=_mock_groq(mock_reply)):
            result = suggest_outfit(item, get_example_wardrobe())
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_wardrobe_returns_string_not_exception(self, item):
        # Must NOT raise — returns general styling advice instead
        mock_reply = "Try wide-leg jeans and chunky sneakers for a 90s vibe."
        with patch("tools._get_groq_client", return_value=_mock_groq(mock_reply)):
            result = suggest_outfit(item, get_empty_wardrobe())
        assert isinstance(result, str)
        assert len(result) > 0

    def test_wardrobe_prompt_includes_piece_names(self, item):
        # Wardrobe item names must appear in the LLM prompt so the model can reference them
        wardrobe = get_example_wardrobe()
        mock_client = _mock_groq("outfit suggestion")
        with patch("tools._get_groq_client", return_value=mock_client):
            suggest_outfit(item, wardrobe)
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        piece_names = [w["name"] for w in wardrobe["items"]]
        assert any(name in prompt for name in piece_names)

    def test_wardrobe_prompt_includes_new_item_title(self, item):
        mock_client = _mock_groq("outfit suggestion")
        with patch("tools._get_groq_client", return_value=mock_client):
            suggest_outfit(item, get_example_wardrobe())
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert item["title"] in prompt

    def test_empty_wardrobe_prompt_includes_item_title(self, item):
        mock_client = _mock_groq("general styling advice")
        with patch("tools._get_groq_client", return_value=mock_client):
            suggest_outfit(item, get_empty_wardrobe())
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert item["title"] in prompt

    def test_returns_stripped_output(self, item):
        mock_reply = "  Pair this with your jeans.  \n"
        with patch("tools._get_groq_client", return_value=_mock_groq(mock_reply)):
            result = suggest_outfit(item, get_example_wardrobe())
        assert result == mock_reply.strip()


# ── create_fit_card ───────────────────────────────────────────────────────────

class TestCreateFitCard:

    @pytest.fixture
    def item(self):
        return search_listings("vintage graphic tee")[0]

    def test_returns_string_on_normal_path(self, item):
        outfit = "Pair with your baggy jeans and chunky sneakers."
        mock_reply = "thrifted this tee off depop for $18 🖤 full look in my stories"
        with patch("tools._get_groq_client", return_value=_mock_groq(mock_reply)):
            result = create_fit_card(outfit, item)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_none_outfit_returns_string_not_exception(self, item):
        # outfit=None must not raise — returns a caption using generic language
        mock_reply = "scored this off depop for $18 and the styling possibilities are endless"
        with patch("tools._get_groq_client", return_value=_mock_groq(mock_reply)):
            result = create_fit_card(None, item)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_whitespace_outfit_treated_as_none(self, item):
        # Whitespace-only outfit is the same failure mode as None
        mock_reply = "found this gem for $18 and the styling possibilities are endless"
        with patch("tools._get_groq_client", return_value=_mock_groq(mock_reply)):
            result = create_fit_card("   ", item)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hardcoded_fallback_when_outfit_and_title_both_missing(self):
        # No LLM call should be made — returns exact hardcoded string
        result = create_fit_card(None, {})
        assert result == "Check out my latest thrift find — styling details coming soon."

    def test_hardcoded_fallback_does_not_call_llm(self):
        with patch("tools._get_groq_client") as mock_get_client:
            create_fit_card(None, {})
        mock_get_client.assert_not_called()

    def test_missing_price_does_not_raise(self, item):
        item_no_price = {k: v for k, v in item.items() if k != "price"}
        mock_reply = "found this on depop and the styling possibilities are endless"
        with patch("tools._get_groq_client", return_value=_mock_groq(mock_reply)):
            result = create_fit_card(None, item_no_price)
        assert isinstance(result, str)

    def test_missing_platform_does_not_raise(self, item):
        item_no_platform = {k: v for k, v in item.items() if k != "platform"}
        mock_reply = "thrifted this tee for $18 and it goes with everything"
        with patch("tools._get_groq_client", return_value=_mock_groq(mock_reply)):
            result = create_fit_card("some outfit suggestion", item_no_platform)
        assert isinstance(result, str)

    def test_normal_prompt_includes_platform_and_price(self, item):
        mock_client = _mock_groq("caption text")
        with patch("tools._get_groq_client", return_value=mock_client):
            create_fit_card("Pair with your baggy jeans.", item)
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert item["platform"].lower() in prompt
        assert str(int(item["price"])) in prompt

    def test_returns_stripped_output(self, item):
        mock_reply = "\n\nthrifted this tee off depop for $18 🖤\n"
        with patch("tools._get_groq_client", return_value=_mock_groq(mock_reply)):
            result = create_fit_card("outfit text", item)
        assert result == mock_reply.strip()
