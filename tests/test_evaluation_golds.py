"""Gold decisions fixed by hand, which a fixture rebuild could undo.

Seventeen committed golds listed a bench member in must_remove (fixed in 9d3c1e4 and
cf95918), so the scorer counted each kept judge as a leak. CONFLICTS are the opposite
decision: in its text the same invented identity is a judge and counsel or a party, so,
privacy first, it stays in must_remove.

A rebuild changes every invented name. Re-derive both tables by reading the new golds;
never delete a failing entry to get a green run.
"""
import json
from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parent.parent / "evaluation" / "corpus"

KEPT_JUDGES = {
    "consiglio_stato/12_auto_2025_25_626senb": [
        "Nicodemo Tagliaferri", "Pizzigoni", "Rosalinda Pizzigoni", "Tagliaferri"],
    "consiglio_stato/13_auto_2025_025_49sent": ["Cavalcanti", "Serafina Cavalcanti"],
    "consiglio_stato/14_auto_2025__17189sent": ["Teodoro Ventimiglia", "Ventimiglia"],
    "consiglio_stato/19_auto_2025_25_538ocau": ["Lo Strano", "Perpetua Lo Strano"],
    "consiglio_stato/22_auto_2026_026_77senb": ["Aristide Fumagalli", "Fumagalli"],
    "consiglio_stato/23_auto_2026_6_4584sent": ["Isotta Malinverni", "Malinverni"],
    "consiglio_stato/24_auto_2026_26_609sent": ["Di Benedetto", "Osvaldo Di Benedetto"],
    "consiglio_stato/25_auto_2026_26_786sent": ["Adelasia Scaramuzza", "Scaramuzza"],
    "corte_conti/14_auto_2003__1095sgcal": ["Gualtiero Piccinini", "Piccinini"],
    "corte_conti/15_auto_2010_rclom-prse": [
        "Adelasia Scaramuzza", "Ermenegildo Trentacoste", "Scaramuzza", "Trentacoste"],
    "corte_conti/21_auto_2019_19_100app2": ["Arcangelo Monteleone", "Monteleone"],
    "merito_civile/01_2019_corte_d_appello_di_ancona": ["Gualtiero Piccinini", "Piccinini"],
    "merito_civile/02_2020_corte_d_appello_di_bari": [
        "Arcangelo Monteleone", "Monteleone", "Teodoro Ventimiglia", "Ventimiglia"],
    "merito_civile/03_2020_corte_d_appello_di_cagliari": [
        "Bonaventura", "Celeste Bonaventura", "Lo Strano", "Malinverni", "Pizzigoni"],
    "merito_civile/04_2022_corte_d_appello_di_catanzaro": [
        "Arcangelo Monteleone", "Ermenegildo Trentacoste", "Monteleone", "Scaramuzza",
        "Trentacoste"],
    "merito_civile/04_2023_corte_d_appello_di_firenze": [
        "Adelasia Scaramuzza", "Mirandolina Zangheratti", "Scaramuzza", "Zangheratti"],
    "tar/21_auto_rpe_2008_714sent": ["Ornella Trevisanato", "Trevisanato"],
}

CONFLICTS = {
    "merito_civile/01_2023_corte_d_appello_di_bari": ["Ornella Trevisanato", "Trevisanato"],
    "merito_civile/03_2022_corte_d_appello_di_brescia": ["Bonaventura", "Celeste Bonaventura"],
    "merito_civile/03_2023_corte_d_appello_di_catanzaro": [
        "Bonaventura", "Celeste Bonaventura"],
    "merito_civile/04_2023_corte_d_appello_di_firenze": [
        "Ermenegildo Trentacoste", "Trentacoste"],
    "merito_civile/05_2022_corte_d_appello_di_firenze": ["Clotilde Pontremoli", "Pontremoli"],
}


def gold(fixture):
    return json.loads((CORPUS / f"{fixture}.gold.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture", sorted(KEPT_JUDGES))
def test_bench_members_stay_in_must_keep(fixture):
    g = gold(fixture)
    assert [v for v in KEPT_JUDGES[fixture]
            if v not in g["must_keep"] or v in g["must_remove"]] == []


@pytest.mark.parametrize("fixture", sorted(CONFLICTS))
def test_judge_and_party_identities_stay_in_must_remove(fixture):
    g = gold(fixture)
    assert [v for v in CONFLICTS[fixture]
            if v not in g["must_remove"] or v in g["must_keep"]] == []
