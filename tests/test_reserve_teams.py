"""Reserve sides (Eerste Divisie 'Jong' teams, U21s) never merge with the first team."""

from team_normalizer import match_key, normalize_team


def test_jong_and_u21_sides_stay_distinct():
    for reserve, first in (("Jong Ajax", "Ajax"), ("Jong PSV", "PSV Eindhoven"),
                           ("Jong FC Utrecht", "FC Utrecht"), ("Arsenal U21", "Arsenal")):
        assert normalize_team(reserve) != normalize_team(first)
        assert match_key(normalize_team(reserve)) != match_key(normalize_team(first))
