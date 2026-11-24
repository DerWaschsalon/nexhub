"""Beute: Zuordnung zum Boss beim Hochladen, Dropraten mit Band (loot.py), Seite nur mit Login."""
from nexhub_api import loot
from nexhub_api.loot import MIN_KILLS

from .conftest import ADMIN, MEMBER
from .test_devices import pair
from .test_runs import nexlog, upload

BOSS_1_END = 1_792_000_000_000 + 300_000 + 100_000  # Boss 1 aus test_runs.fight(): Start plus Dauer


def summary(kills_with: int, kills_without: int, tracked: bool = True) -> list[dict]:
    """So viele Siege über „Boss“, davon `kills_with` mit dem Gegenstand 7."""
    boss = {"mob": 1, "name": "Boss", "killed": True}
    runs = [{"loot_tracked": tracked, "bosses": [{**boss, "loot": [{"item_id": 7, "count": 1}]}]}] * kills_with
    return runs + [{"loot_tracked": tracked, "bosses": [{**boss, "loot": []}]}] * kills_without


def test_rate_mit_band():
    item = loot.table(summary(10, 30))[0]["items"][0]
    assert (item["drops"], item["kills"], item["one_in"]) == (10, 40, 4.0)
    assert item["one_in_low"] < 4.0 < item["one_in_high"]
    low, high = loot.wilson(10, 40)
    assert round(low, 3) == 0.156 and round(high, 3) == 0.376  # von Hand nachgerechnet, 90 %


def test_zu_wenige_siege_nur_zaehlung():
    item = loot.table(summary(2, MIN_KILLS - 3))[0]["items"][0]
    assert item["drops"] == 2 and item["one_in"] is None


def test_nur_runs_die_beute_melden_und_nur_siege():
    assert loot.table(summary(5, 5, tracked=False)) == []
    wipe = [{"loot_tracked": True, "bosses": [{"mob": 1, "name": "Boss", "killed": False, "loot": []}]}]
    assert loot.table(wipe) == []


def test_zweimal_derselbe_gegenstand_zaehlt_als_ein_sieg():
    double = [{"loot_tracked": True, "bosses": [{"mob": 1, "name": "Boss", "killed": True,
                                                 "loot": [{"item_id": 7, "count": 1}, {"item_id": 7, "count": 2}]}]}]
    assert loot.count(double)[0].drops == {7: 1}


def test_hochladen_ordnet_beute_dem_boss_zu(client, as_user):
    admin = as_user(ADMIN)
    token = pair(client, admin)
    drops = [{"t_ms": BOSS_1_END + 5_000, "item_id": 110430050, "count": 1},  # nach Boss 1 (besiegt)
             {"t_ms": BOSS_1_END - 200_000, "item_id": 9, "count": 1}]  # vor dem ersten Sieg: Gegner auf dem Weg
    run_id = upload(client, token, nexlog(loot=drops)).json()["id"]
    bosses = admin.get(f"/api/runs/{run_id}").json()["summary"]["bosses"]
    assert bosses[0]["loot"] == [{"item_id": 110430050, "count": 1}] and bosses[1]["loot"] == []

    page = as_user(MEMBER).get("/api/loot").json()
    assert page["min_kills"] == MIN_KILLS and len(page["dungeons"]) == 1
    dungeon = page["dungeons"][0]
    assert (dungeon["dungeon"], dungeon["runs"]) == ("Ferocious Horn Den", 1)
    assert dungeon["bosses"][0]["kills"] == 1 and dungeon["bosses"][0]["items"][0]["item_id"] == 110430050
    assert client.get("/api/loot").status_code == 401


def test_runs_ohne_beute_meldung_fehlen(client, as_user):
    admin = as_user(ADMIN)
    upload(client, pair(client, admin), nexlog())  # ältere NexBoard: das Feld fehlt
    assert admin.get("/api/loot").json()["dungeons"] == []
