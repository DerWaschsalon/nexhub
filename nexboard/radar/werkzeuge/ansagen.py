"""Übernimmt die Boss-Ansagen des A2Tools-Plugins „Boss Callouts“ (boss-telegraph) nach
radar/ansagen.json und legt je Boss einen Schalter in radar/meldungen.json an.

Das Plugin (taengu/A2Tools-Plugins, GPL-3.0) hat seine Liste aus den Spieltabellen erzeugt: je Boss
die Zeilen, die das Spiel bei einem Skill einblendet, mit Skill-ID und Dauer der Cast-Leiste, dazu
von Hand geprüfte Mechaniken (kurze Anweisung, Dauer des Buffs, Wellen, Reihenfolge). Die Zeilen
selbst sind Spieltext (c) NCSOFT. Übernommen werden nur Deutsch und Englisch.

Aufruf (im Ordner nexboard/radar): python -m werkzeuge.ansagen
"""
import json
import urllib.request
from pathlib import Path

# Fester Stand, damit ein neuer Lauf nur auf Wunsch etwas ändert (nach einem Spielpatch erhöhen)
STAND = "f206c25c4960d1180d143776e48e4360cdf44f78"
QUELLE = ("https://raw.githubusercontent.com/taengu/A2Tools-Plugins/"
          f"{STAND}/plugins/boss-telegraph/bosses.js")
ORDNER = Path(__file__).parents[1] / "radar"
UMBENENNEN = {"Fire Temple": "Feuertempel"}  # wie in werkzeuge/bosse.py
OHNE_DUNGEON = "Weltbosse und Sonstige"  # Bosse, denen das Plugin keinen Dungeon gibt
# Auslöser im Plugin -> Art im Radar (leiste = 0x3809, skill = 0x3802, effekt = 0x382A)
ARTEN = {"cast": "leiste", "use": "skill", "abnormal": "effekt"}


def laden() -> dict:
    """Die Liste des Plugins: eine JS-Datei, die genau ein JSON-Objekt zuweist."""
    with urllib.request.urlopen(QUELLE, timeout=30) as antwort:
        text = antwort.read().decode()
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


class Umwandlung:
    """Liest die Plugin-Liste und baut daraus Bosse und Ansagen im Format von radar/ansagen.json."""

    def __init__(self, plugin: dict) -> None:
        self.plugin = plugin

    def text(self, nummer: int | None) -> dict | None:
        """Ein Text auf Deutsch und Englisch (fehlt Deutsch, gilt Englisch)."""
        if nummer is None:
            return None
        eintrag = self.plugin["texts"][nummer]
        en = eintrag["en"].replace("\n", " ").strip()
        return {"de": (eintrag.get("de") or en).replace("\n", " ").strip(), "en": en}

    def dungeon(self, boss: dict) -> str:
        name = self.text(self.plugin["groups"][boss["g"]].get("n"))
        return UMBENENNEN.get(name["en"], name["en"]) if name else OHNE_DUNGEON

    def bosse(self) -> dict:
        return {slug: {"name": self.text(b["n"]), "dungeon": self.dungeon(b), "skills": b.get("s", [])}
                for slug, b in self.plugin["bosses"].items()}

    def ruf(self, r: dict) -> dict:
        ruf = {"schluessel": r["k"], "art": ARTEN[r["t"]], "id": r["id"], "boss": r["b"], "gruppe": gruppe(r["b"]),
               "vorlauf": r.get("lead", 0) / 1000, "zeile": self.text(r.get("line")),
               "anweisung": self.text(r.get("act")), "buff": self.text(r.get("n")),
               "braucht_boss": bool(r.get("bind")), "wellen": bool(r.get("waves")), "reihe": r.get("mark")}
        if r.get("phase"):
            ph = r["phase"]
            ruf["phase"] = {"effekt": ph["a"], "sekunden": ph["ms"] / 1000,
                            "anzeige": self.text(ph["label"]), "name": self.text(ph["n"])}
        return {k: v for k, v in ruf.items() if v not in (None, False)}

    def alles(self) -> dict:
        return {
            "_quelle": ("Boss-Ansagen aus dem Plugin „Boss Callouts“ von taengu/A2Tools-Plugins (GPL-3.0), "
                        f"Stand {STAND[:7]}, übernommen mit werkzeuge/ansagen.py. Zeilen und Namen: "
                        "Spieltext (c) NCSOFT."),
            "sicher": self.text(self.plugin["safe"]),
            "bosse": self.bosse(),
            "rufe": [self.ruf(r) for r in self.plugin["calls"]],
        }


def gruppe(slug: str) -> str:
    """Schalter auf der NexBoard-Seite: einer je Boss."""
    return "ansage_" + slug.replace("-", "_")


def schalter_eintragen(meldungen: dict, daten: dict) -> None:
    """Je Boss ein Schalter in meldungen.json, beim Dungeon des Bosses; alte Ansage-Schalter raus."""
    for gruppen in meldungen["dungeons"].values():
        for alt in [g for g in gruppen if g.startswith("ansage_")]:
            del gruppen[alt]
    for slug in sorted({r["boss"] for r in daten["rufe"]}):
        boss = daten["bosse"][slug]
        meldungen["dungeons"].setdefault(boss["dungeon"], {})[gruppe(slug)] = f"{boss['name']['de']}: Ansagen"


def main() -> None:
    daten = Umwandlung(laden()).alles()
    (ORDNER / "ansagen.json").write_text(json.dumps(daten, indent=1, ensure_ascii=False) + "\n")
    datei = ORDNER / "meldungen.json"
    meldungen = json.loads(datei.read_text())
    schalter_eintragen(meldungen, daten)
    datei.write_text(json.dumps(meldungen, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(daten['rufe'])} Ansagen von {len(daten['bosse'])} Bossen übernommen")


if __name__ == "__main__":
    main()
