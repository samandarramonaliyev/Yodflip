import pytest

from decks.models import Deck
from decks.parsing import cards_to_csv, csv_to_cards, parse_bulk, split_line


@pytest.mark.parametrize(
    "line,expected",
    [
        ("apple - olma", ("apple", "olma")),
        ("apple\tolma", ("apple", "olma")),
        ("apple: olma", ("apple", "olma")),
        ("apple-olma", ("apple", "olma")),
        ("well-known - mashhur", ("well-known", "mashhur")),
        ("to look up – qidirib topmoq", ("to look up", "qidirib topmoq")),
        ("mother-in-law\tqaynona", ("mother-in-law", "qaynona")),
        ("time: vaqt - soat", ("time: vaqt", "soat")),
    ],
)
def test_split_line(line, expected):
    assert split_line(line) == expected


@pytest.mark.parametrize("line", ["", "   ", "noseparator", "apple - ", " - olma"])
def test_split_line_invalid(line):
    assert split_line(line) is None


def test_parse_bulk_reports_bad_lines_and_articles():
    text = "der Hund - it\n\nKatze\ndas Haus: uy\nbad line\n"
    cards, bad = parse_bulk(text, "de")
    assert [c["term"] for c in cards] == ["der Hund", "das Haus"]
    assert cards[0]["article"] == "der"
    assert cards[1]["article"] == "das"
    assert bad == [3, 5]


def test_parse_bulk_english_has_no_articles():
    cards, _ = parse_bulk("die - o'lmoq", "en")
    assert cards[0]["article"] == ""


def test_csv_roundtrip():
    rows = [{"term": "apple", "translation": "olma", "definition": "a fruit", "example": "", "article": ""}]
    assert csv_to_cards(cards_to_csv(rows)) == rows


def test_csv_headerless_semicolon():
    assert csv_to_cards("apple;olma\nbread;non\n")[1]["translation"] == "non"


@pytest.mark.django_db
def test_bulk_endpoint(api, user):
    deck = Deck.objects.create(owner=user, name="Test", track="en")
    r = api.post(f"/api/decks/{deck.id}/bulk/", {"text": "cat - mushuk\ndog: it\nnope"}, format="json")
    assert r.status_code == 201
    assert r.data == {"added": 2, "bad_lines": [3]}
    assert deck.cards.count() == 2
