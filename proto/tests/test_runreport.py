"""RunReport: das Format, das NexBoard, Hub und Bot für einen Run teilen."""
import pytest
from pydantic import ValidationError

from nexproto.runreport import RunReport

SPIELER = [{"name": "Gamunex", "cls": "chanter", "damage": 1000, "dps": 10}]
RUN = {"dungeon": "Fire Temple", "difficulty": "Normal", "dungeon_id": 600123, "bosses_total": 2,
       "bosses_killed": 2, "complete": True, "start_ms": 1, "end_ms": 2, "fight_ms": 100, "players": SPIELER,
       "bosses": [{"name": "Kromede", "mob": 2400012, "killed": True, "duration_ms": 50, "players": SPIELER}]}


def test_gueltiger_bericht():
    assert RunReport.model_validate(RUN).bosses[0].players[0].name == "Gamunex"


@pytest.mark.parametrize("kaputt", [{"players": []}, {"dungeon": ""}, {"unbekannt": 1},
                                    {"players": [{"name": "x", "damage": -1, "dps": 0}]}])
def test_kaputter_bericht(kaputt):
    with pytest.raises(ValidationError):
        RunReport.model_validate({**RUN, **kaputt})
