"""Tests for the number parsing / transforms module."""

import pytest

from src.transforms import apply_transform, identity, instagram_comments, instagram_likes, parse_number


class TestParseNumber:
    """Tests for parse_number()."""

    def test_plain_integer(self):
        assert parse_number("1234") == 1234

    def test_integer_with_commas(self):
        assert parse_number("1,234") == 1234

    def test_integer_with_dots_as_thousands(self):
        assert parse_number("1.234") == 1234

    def test_large_number_with_commas(self):
        assert parse_number("1,234,567") == 1234567

    def test_large_number_with_dots(self):
        assert parse_number("1.234.567") == 1234567

    def test_abbreviated_k(self):
        assert parse_number("1.2K") == 1200

    def test_abbreviated_k_lowercase(self):
        assert parse_number("1.2k") == 1200

    def test_abbreviated_m(self):
        assert parse_number("3.5M") == 3500000

    def test_abbreviated_k_with_comma(self):
        assert parse_number("1,2K") == 1200

    def test_turkish_bin(self):
        # Turkish "B" = bin = 1000
        assert parse_number("1,2B") == 1200

    def test_turkish_milyon(self):
        assert parse_number("3,5Mn") == 3500000

    def test_aria_label_style(self):
        assert parse_number("1,234 likes") == 1234

    def test_aria_label_with_text(self):
        assert parse_number("Liked by 5,678 people") == 5678

    def test_zero(self):
        assert parse_number("0") == 0

    def test_none_input(self):
        assert parse_number(None) is None

    def test_empty_string(self):
        assert parse_number("") is None

    def test_dash(self):
        assert parse_number("-") is None

    def test_double_dash(self):
        assert parse_number("--") is None

    def test_na(self):
        assert parse_number("N/A") is None

    def test_whitespace(self):
        assert parse_number("   ") is None

    def test_just_text(self):
        assert parse_number("likes") is None

    def test_number_with_whitespace(self):
        assert parse_number("  1234  ") == 1234

    def test_10k(self):
        assert parse_number("10K") == 10000

    def test_100k(self):
        assert parse_number("100K") == 100000

    def test_1m(self):
        assert parse_number("1M") == 1000000

    def test_round_k(self):
        assert parse_number("5K") == 5000

    def test_large_abbreviated(self):
        assert parse_number("2.1M") == 2100000


class TestInstagramLikes:
    @pytest.mark.parametrize("text,expected", [
        ("1,234 likes, 56 comments - username: caption", 1234),
        ("1.234 Beğeni, 56 Yorum - username", 1234),
        ("0 likes, 0 comments", 0),
        ("No likes here", None),
        (None, None),
        ("", None),
        ("100 Likes, 5 comments - @user", 100),
    ])
    def test_instagram_likes(self, text, expected):
        assert instagram_likes(text) == expected


class TestInstagramComments:
    @pytest.mark.parametrize("text,expected", [
        ("1,234 likes, 56 comments - username: caption", 56),
        ("1.234 Beğeni, 56 Yorum - username", 56),
        ("0 likes, 0 comments", 0),
        ("No engagement here", None),
        (None, None),
        ("", None),
        ("5 likes, 100 Comments", 100),
    ])
    def test_instagram_comments(self, text, expected):
        assert instagram_comments(text) == expected


class TestIdentity:
    def test_strips_whitespace(self):
        assert identity("  username  ") == "username"

    def test_plain_string(self):
        assert identity("john_doe") == "john_doe"

    def test_none_returns_none(self):
        assert identity(None) is None

    def test_empty_string(self):
        assert identity("") == ""


class TestApplyTransform:
    def test_parse_number_dispatch(self):
        assert apply_transform("parse_number", "1,234") == 1234

    def test_instagram_likes_dispatch(self):
        assert apply_transform("instagram_likes", "500 likes, 10 comments") == 500

    def test_instagram_comments_dispatch(self):
        assert apply_transform("instagram_comments", "500 likes, 10 comments") == 10

    def test_identity_dispatch(self):
        assert apply_transform("identity", "  handle  ") == "handle"

    def test_unknown_transform_raises(self):
        with pytest.raises(ValueError, match="Unknown transform"):
            apply_transform("nonexistent", "text")
