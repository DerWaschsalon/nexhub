"""Boss-Ansagen wie im A2Tools-Plugin „Boss Callouts“ (taengu/A2Tools-Plugins, GPL-3.0, logic.js),
nach Python übertragen. Die Daten stehen in data/callouts.json (werkzeuge/ansagen.py).

Gesagt wird nur, was das Spiel ohnehin zeigt: die Zeile des Bosses, die Zeit seiner Cast-Leiste, ein
Buff auf ihm und wie lange er liegt. Die von Hand geprüften Mechaniken bringen eine kurze Anweisung
mit („Lila — keine Magieangriffe“), einen Countdown, solange der Buff liegt, und danach „Wieder
angreifen“. Bei Vakrons Sprung piept es zu jeder Welle.

Mit „Nur was mich betrifft“ schweigt ein Ruf, dessen Cast auf einen anderen Spieler zielt oder dessen
Effekt auf einem anderen Spieler liegt. Casts ohne Ziel oder auf den Boss selbst (Flächen, Angriffe auf
alle) bleiben.

Die Pakete kommen von jedem Wesen, auch von Spielern. Welcher Boss ein Wesen ist, merkt sich die Klasse
erst, wenn es einen der Skills dieses Bosses einsetzt (eine halbe Stunde lang). Nur so lässt sich ein
Buff, den jedes Monster bekommen kann (Raserei, Benommenheit), dem richtigen Boss zuordnen.
"""
from __future__ import annotations

from .fight import FightEvents
from .gamedata import CALLOUTS
from .rules import COLORS, Rule
from .warning_board import WAVE, WarningBoard

REPEAT_S = 1.2  # derselbe Auslöser desselben Wesens so kurz danach: nur einmal
NO_BAR_S = 4.0  # so lange steht eine Ansage ohne Cast-Leiste
SAFE_S = 2.5  # „Wieder angreifen“
WAVE_GAP_S = 0.4  # mehrere Geschosse einer Welle: ein Piepton
WAVES_FOR_S = 8.0  # so lange nach dem Skill zählen seine Wellen
REMEMBER_BOSS_S = 30 * 60
ROW_GAP_S = 6.0  # ein Zeichen so lange nach dem letzten beginnt eine neue Reihe
ROW_SHOW_S = 12.0  # die Reihe bleibt stehen, solange sie abläuft
PHASE_S = (0.5, 120.0)  # Dauer eines Buffs, auf diesen Bereich begrenzt
JUST_SAID_S = 6.0  # Anweisung kam eben schon: zum Beginn der Phase nicht noch einmal sagen
PREVIEW_PHASE_S = 5.0  # ▶ auf der NexBoard-Seite: die Phase so lange, wie im Plugin
PREVIEW_NOBODY = -1  # Wesen der Vorschau
BAR, SKILL, EFFECT = "leiste", "skill", "effekt"  # Arten der Auslöser in den Daten
PAGE_KINDS = {BAR: "Zauber", SKILL: "Fertigkeit", EFFECT: "Buff am Boss"}  # Wörter des Plugins


class Callouts:
    """Hört auf Cast-Leiste, Skill, Wellen und Effekte und gibt die passenden Ansagen an die Warn-Anzeige."""

    def __init__(self, board: WarningBoard, fight: FightEvents | None = None, data: dict = CALLOUTS) -> None:
        self.board = board
        self.bosses = data["bosse"]
        self.safe = data["sicher"]
        self.calls: dict[tuple[str, int], list[dict]] = {}  # (Art, ID) → Rufe (einer je Boss)
        self.phase_calls: dict[int, list[dict]] = {}  # Buff-ID → Rufe mit dieser Phase
        self.users: dict[int, set[str]] = {}  # Skill → Bosse, die ihn einsetzen
        for call in data["rufe"]:
            self.calls.setdefault((call["art"], call["id"]), []).append(call)
            if "phase" in call:
                self.phase_calls.setdefault(call["phase"]["effekt"], []).append(call)
            if call["art"] != EFFECT:
                self.users.setdefault(call["id"], set()).add(call["boss"])
        for slug, boss in self.bosses.items():
            for skill in boss["skills"]:
                self.users.setdefault(skill, set()).add(slug)
        self.effects = {i for kind, i in self.calls if kind == EFFECT} | set(self.phase_calls)
        self.beings: dict[int, tuple[set[str], float]] = {}  # Entity → (Bosse, zuletzt gesehen)
        self.last: dict[tuple[int, str, int], float] = {}  # (Entity, Art, ID) → Zeit
        self.said: dict[int, float] = {}  # id(Ruf) → Zeit der letzten Ansage
        self.phases: dict[tuple[int, int], tuple[dict, float]] = {}  # (Entity, Instanz) → (Ruf, Ende)
        self.waves: dict[tuple[int, int], list] = {}  # (Entity, Skill) → [Ruf, Beginn, letzter Piep]
        self.rows: dict[tuple[int, str], tuple[list[str], float]] = {}  # (Entity, Reihe) → (Wörter, zuletzt)
        self.by_key = {call["schluessel"]: call for call in data["rufe"]}
        self.preview_phases: list[tuple[float, dict]] = []  # (fällig um, Ruf)
        if fight:
            fight.effect_ids |= self.effects
            fight.cast.connect(self.skill)
            fight.cast_bar.connect(self.bar)
            fight.wave.connect(self.wave)
            fight.effect.connect(self.effect)
            fight.effect_gone.connect(self.effect_gone)

    @property
    def settings(self) -> dict:
        return self.board.settings

    # ---------- Eingänge (aus dem Mitschnitt-Thread) ----------
    def bar(self, caster: int, skill: int, target: int | None = None) -> None:
        self._trigger(BAR, caster, skill, target)

    def skill(self, caster: int, skill: int, target: int | None = None) -> None:
        self._trigger(SKILL, caster, skill, target)

    def effect(self, being: int, instance: int, effect: int, duration: float) -> None:
        if self.board.foreign(being):
            return  # Effekt auf einem anderen Spieler
        for call in self.phase_calls.get(effect, []):
            if self._on(call):
                self._phase_begins(call, being, instance, duration)
                break
        self._trigger(EFFECT, being, effect)

    def effect_gone(self, being: int, instance: int) -> None:
        self._phase_ends((being, instance))

    def wave(self, caster: int, skill: int) -> None:
        w = self.waves.get((caster, skill))
        now = self.board.clock()
        if not w or now - w[1] > WAVES_FOR_S or now - w[2] < WAVE_GAP_S:
            return
        w[2] = now
        if self._on(w[0]) and self.settings["wellen_ton"]:
            self.board.sounds.append((WAVE, ""))  # kurzer Piepton

    def test(self, key: str) -> None:
        """▶ auf der NexBoard-Seite: der Ruf, wie ein Kampf ihn bringt (mit eigenen Worten), danach seine
        Phase auf 5 s gekürzt und „Wieder angreifen“. Gilt auch für einen abgehakten Ruf."""
        call = self.by_key.get(key)
        if not call:
            return
        now = self.board.clock()
        if "reihe" in call:
            self._row(call, PREVIEW_NOBODY, now)
        else:
            self._call(call, PREVIEW_NOBODY, now)
        if "phase" in call:
            self.preview_phases.append((now + min(call.get("vorlauf") or 1.8, 3.0), call))

    def tick(self) -> None:
        """Abgelaufene Phasen beenden (der Server schickt das Ende nicht immer), Vorschau-Phasen beginnen."""
        now = self.board.clock()
        for due, call in [p for p in self.preview_phases if p[0] <= now]:
            self.preview_phases.remove((due, call))
            self._phase_begins(call, PREVIEW_NOBODY, PREVIEW_NOBODY, PREVIEW_PHASE_S)
        for key, (_call, end) in list(self.phases.items()):
            if end <= now:
                self._phase_ends(key)

    # ---------- Ablauf ----------
    def _trigger(self, kind: str, being: int, i: int, target: int | None = None) -> None:
        now = self.board.clock()
        if kind != EFFECT:
            self._learn(being, i, now)
        if self.board.foreign(target):
            return  # zielt auf einen anderen Spieler („Nur was mich betrifft“)
        calls = self.calls.get((kind, i))
        call = calls and self._choose(calls, being, now)
        if not call or not self._on(call):
            return
        last = self.last.get((being, kind, i))
        self.last[(being, kind, i)] = now
        if last is not None and now - last < REPEAT_S:
            return
        if "reihe" in call:
            self._row(call, being, now)
        else:
            self._call(call, being, now)

    def _learn(self, being: int, skill: int, now: float) -> None:
        """Setzt ein Wesen einen Skill eines Bosses ein, ist es (vermutlich) dieser Boss."""
        bosses = self.users.get(skill)
        if bosses:
            known = self.beings.get(being, (set(), now))[0]
            self.beings[being] = (known | bosses, now)

    def _choose(self, calls: list[dict], being: int, now: float) -> dict | None:
        """Von den Rufen eines Auslösers (einer je Boss) der für dieses Wesen. Ist das Wesen unbekannt,
        schweigt ein Ruf, der seinen Boss kennen muss."""
        bosses, seen = self.beings.get(being, (set(), -REMEMBER_BOSS_S))
        if now - seen < REMEMBER_BOSS_S:
            for call in calls:
                if call["boss"] in bosses:
                    return call
        return next((c for c in calls if not c.get("braucht_boss")), None)

    def _on(self, call: dict) -> bool:
        """Boss nicht abgeschaltet (Schalter je Boss), Ruf nicht abgehakt, passender Dungeon."""
        return call["schluessel"] not in self.settings["ruf_aus"] and self.board.group_on(call["gruppe"])

    def _call(self, call: dict, being: int, now: float) -> None:
        big, small, say = self._words(call)
        self.said[id(call)] = now
        rule = Rule(big, small or self._boss(call), call.get("vorlauf") or NO_BAR_S, COLORS["GELB"],
                    call["gruppe"], speak=say)
        self.board.trigger(rule, now)
        if call.get("wellen"):
            self.waves[(being, call["id"])] = [call, now, 0.0]

    def _words(self, call: dict) -> tuple[str, str, tuple[str, ...]]:
        """(groß, klein, gesprochen) nach dem eingestellten Stil: beides, nur Anweisung, nur Zeile."""
        own = self._own_words(call)
        if own:
            return own, "", (own,)  # eigene Worte gelten statt des Rufs, egal welcher Stil
        style = self.settings["ansage_stil"]
        line, instruction = self._text(call.get("zeile")), self._text(call.get("anweisung"))
        buff = self._text(call.get("buff")) if call["art"] == EFFECT else ""
        if style == "zeile":
            big = line or instruction or buff
            return big, "", (big,)
        if style == "anweisung":
            big = instruction or line or buff
            return big, "" if instruction else buff, (big,)
        if instruction and line:
            return instruction, line, (instruction, line)
        big = instruction or line or buff
        return big, buff if buff and line else "", (big,)

    def _row(self, call: dict, being: int, now: float) -> None:
        """Eine Reihenfolge, die der Boss Zeichen für Zeichen zeigt (Talisras Speere: Dunkel, Dunkel,
        Licht): jedes Zeichen gesagt, angezeigt die Reihe bis hierher."""
        key = (being, call["reihe"])
        words, last = self.rows.get(key, ([], -ROW_GAP_S))
        if now - last >= ROW_GAP_S:
            words = []
        word = self._own_words(call) or self._text(call.get("anweisung"))
        words = words + [word]
        self.rows[key] = (words, now)
        self.board.trigger(Rule(" → ".join(words), self._boss(call), ROW_SHOW_S, COLORS["GELB"], call["gruppe"],
                                speak=(word,)), now)

    def _phase_begins(self, call: dict, being: int, instance: int, duration: float) -> None:
        """Der Buff einer geprüften Mechanik liegt: Countdown über seine echte Dauer."""
        now = self.board.clock()
        phase = call["phase"]
        duration = min(max(duration or phase["sekunden"], PHASE_S[0]), PHASE_S[1])
        line_only = self.settings["ansage_stil"] == "zeile"
        shown = (line_only and self._text(phase.get("name"))) or self._text(phase.get("anzeige")) \
            or self._text(call.get("anweisung"))
        fresh = (being, instance) not in self.phases
        self.phases[(being, instance)] = (call, now + duration)
        just_said = now - self.said.get(id(call), -JUST_SAID_S) < JUST_SAID_S
        say = (shown,) if fresh and not just_said else ()
        small = "" if line_only else self._text(phase.get("name"))
        self.board.trigger(Rule(shown, small, duration, COLORS["ORANGE"], call["gruppe"], speak=say), now)

    def _phase_ends(self, key: tuple[int, int]) -> None:
        entry = self.phases.pop(key, None)
        if not entry:
            return
        call = entry[0]
        if any(c is call for c, _ in self.phases.values()):
            return  # dieselbe Mechanik läuft noch auf einem anderen: noch nicht sicher
        safe = self._text(self.safe)
        self.board.trigger(Rule(safe, self._boss(call), SAFE_S, COLORS["GRUEN"], call["gruppe"], speak=(safe,)))

    # ---------- Hilfen ----------
    def _own_words(self, call: dict) -> str:
        """Eigene Worte für diesen Ruf von der NexBoard-Seite, sonst leer."""
        return str(self.settings["eigene_worte"].get(call["schluessel"], "")).strip()

    def _boss(self, call: dict) -> str:
        return self._text(self.bosses[call["boss"]]["name"])

    def _text(self, texts: dict | None) -> str:
        """Der Text in der eingestellten Sprache (Deutsch oder Englisch)."""
        return texts[self.settings["sprache"]] if texts else ""


def short_texts(language: str, data: dict = CALLOUTS) -> list[str]:
    """Die kurzen Anweisungen der Boss-Ansagen und „Wieder angreifen“ zum Vorab-Erzeugen (die langen
    Boss-Zeilen nicht, die werden beim ersten Mal erzeugt, ca. 0,4 s)."""
    texts = [data["sicher"][language]]
    for call in data["rufe"]:
        texts += [call["anweisung"][language]] if "anweisung" in call else []
        texts += [call["phase"]["anzeige"][language]] if "phase" in call else []
    return texts


def page_list(data: dict = CALLOUTS) -> dict[str, list[dict]]:
    """Die Rufe je Schalter (Boss) für die NexBoard-Seite: Schlüssel, Art und die Vorgabe auf Deutsch.
    Zwei Rufe mit demselben Schlüssel (Vakrons Sprung, normal und leicht) sind eine Zeile."""
    listing: dict[str, list[dict]] = {}
    seen: set[str] = set()
    for call in data["rufe"]:
        if call["schluessel"] in seen:
            continue
        seen.add(call["schluessel"])
        default = (call.get("anweisung") or call.get("zeile") or call.get("buff"))["de"]
        listing.setdefault(call["gruppe"], []).append(
            {"schluessel": call["schluessel"], "art": PAGE_KINDS[call["art"]], "vorgabe": default,
             "zeile": call["zeile"]["de"] if call.get("anweisung") and call.get("zeile") else ""})
    return listing
