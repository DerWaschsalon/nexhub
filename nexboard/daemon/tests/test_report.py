"""Run-Bericht (report.py): das RunReport-Format, das der Hub an TheWashBot weiterleitet."""
import base64

from test_runs import DUNGEON, fight

from deckbar_daemon.dps import fight_view
from deckbar_daemon.report import run_report
from deckbar_daemon.run_model import Run, parse_fight


def run_from_history():
    run = Run(DUNGEON)
    run.fights = [parse_fight(fight(2400011, 0, dur_s=60), you_actor=2),
                  parse_fight(fight(2400012, 120, dur_s=90, dmg=(400, 600)), you_actor=2)]
    run.complete = True
    run.rename({"Mo***n|ranger": "Morgan"})
    return run


def test_bericht_passt_zum_vertrag():
    r = run_report(run_from_history())
    assert r.dungeon_id == DUNGEON and r.dungeon
    assert r.bosses_total == 2 and r.bosses_killed == 2 and r.fight_ms == 150_000
    assert sorted(p.name for p in r.players) == ["Gamunex", "Morgan"]
    g = next(p for p in r.players if p.name == "Gamunex")
    assert g.damage == 1000 and g.dps == round(1000 / 150)
    assert [len(b.players) for b in r.bosses] == [2, 2] and r.bosses[1].duration_ms == 90_000
    assert r.image_webp is None


async def test_bild_einmal_gezeichnet_und_nach_umbenennen_neu(monkeypatch):
    from deckbar_daemon import run_image as runs_mod

    calls = []
    monkeypatch.setattr(runs_mod, "render_run", lambda r: calls.append(1) or b"RIFF\0\0\0\0WEBPbild")
    r = run_from_history()
    assert await runs_mod.run_image(r) == await runs_mod.run_image(r) and len(calls) == 1
    r.rename(dict(r.names))  # gleiche Namen: Bild bleibt
    await runs_mod.run_image(r)
    assert len(calls) == 1
    key = next(p.key for f in r.fights for p in f.players)
    r.rename({key: "Neuer Name"})  # andere Namen: neu zeichnen
    await runs_mod.run_image(r)
    assert len(calls) == 2
    image = run_report(r, await runs_mod.run_image(r)).image_webp
    assert image and base64.b64decode(image).startswith(b"RIFF")


def test_fight_view_keeps_party_flag_or_none():
    rows = [{"name": "Aria", "cls": "spiritmaster", "dps": 30000, "dmg": 3_000_000, "pct": 40.0, "you": True,
             "party": True}]
    v = fight_view({"target": "Nuakum", "targetId": 77, "boss": True, "timeMs": 95_400, "hp": 0.0, "rows": rows})
    assert v["target_id"] == 77 and v["boss"] and v["time"] == 95 and v["rows"][0]["party"] is True
    old = fight_view({"rows": [{"name": "X", "dps": 1, "dmg": 1}]})  # A2Tools-Stream, altes deckbar-capture
    assert old["rows"][0]["party"] is None
