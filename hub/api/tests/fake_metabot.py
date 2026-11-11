"""Nachgebaute Gegenstandsseiten von MetaBot.GG für Tests: nur das Gerüst, das metabot.py liest,
Inhalte erfunden. Englisch unter /en/aion-2/items/, deutsch unter /de_DE/aion-2/items/."""
from __future__ import annotations

import httpx

HOST = "metabot.gg"


def page(rolls: list[tuple[str, str, str]], skills: dict[str, list[tuple[str, str]]], level: int = 1) -> str:
    """rolls: (Name, Bereich wie „+7.9% – +9.1%“, Chance wie „6%“); skills: Klasse → (Skill, Chance)."""
    rows = "".join(f'<tr><th scope="row">{n}</th><td class="B32I9a_num">{r}</td><td><span>'
                   f'<span class="_8ziuIG_inlineVal">{c}</span></span></td></tr>' for n, r, c in rolls)
    table = (f'<h3 class="R2pfCq_h3">Random stats ({len(rolls)} rolls)</h3><div class="B32I9a_gridWrap">'
             f'<table class="B32I9a_grid B32I9a_gridCompact"><tbody>{rows}</tbody></table></div>') if rolls else ""
    classes = "".join(
        f'<tr><th scope="row"><span>{cls}<span class="_8z5TwW_sub">{len(opts)} skills · up to Lv. {level}</span>'
        f'</span></th><td><span class="_8z5TwW_skillChips">'
        + "".join(f'<span class="_8z5TwW_skillChip"><a class="B32I9a_nameLink"><span class="B32I9a_nameText">{n}'
                  f'</span></a><span class="_8z5TwW_sub">{c}</span></span>' for n, c in opts)
        + "</span></td></tr>" for cls, opts in skills.items())
    options = f"<h2>Random skill options</h2><table><tbody>{classes}</tbody></table>" if skills else ""
    return f"<html><body>{table}{options}</body></html>"


# Testbogen wie in fake_nc.item(): Mehrfachtreffer-Chance 9.1 % ist ein Wurf dieses Bogens
BOW_EN = page([("Mehrfachtreffer-Chance", "+7.9% – +9.1%", "6%"), ("Kampftempo", "+10.6% – +12.3%", "4%"),
               ("MP", "+168 – +200", "90%")], {"Ranger": [("Zielpfeil", "50%"), ("Orkanpfeil", "50%")]})
BOW_DE = page([("Mehrfachtreffer", "+7,9 % – +9,1 %", "6 %"), ("Kampftempo", "+10,6 % – +12,3 %", "4 %"),
               ("MP", "+168 – +200", "90 %")], {"Waldläufer": [("Zielpfeil", "50 %"), ("Orkanpfeil", "50 %")]})


class FakeMetaBot:
    """`pages` je Adresse (Pfad ohne Sprache, z. B. „testbogen“) die Seite je Sprache; sonst 404."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.pages: dict[str, dict[str, str]] = {"testbogen": {"en": BOW_EN, "de_DE": BOW_DE}}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url.path)
        parts = request.url.path.strip("/").split("/")  # en / aion-2 / items / <name>
        found = self.pages.get(parts[-1], {}).get(parts[0])
        return httpx.Response(200, text=found) if found else httpx.Response(404)
