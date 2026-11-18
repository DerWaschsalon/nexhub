"""PoE-Bausteine ohne Spiel: Spielerkennung, Client.txt, Guide-Bau, Tracker, Anzeige, PoB, XP."""
import base64
import zlib
from pathlib import Path, PureWindowsPath

from deckbar_daemon.poe.client_log import ClientLog, LevelUp, ZoneEntered, parse_line
from deckbar_daemon.poe.games import POE1, POE2, linux_path, steam_libraries
from deckbar_daemon.poe.leveling import pob
from deckbar_daemon.poe.leveling.data import default_guide, load
from deckbar_daemon.poe.leveling.device_view import device_line
from deckbar_daemon.poe.leveling.experience import experience
from deckbar_daemon.poe.leveling.guide import GuideBuilder
from deckbar_daemon.poe.leveling.markup import AREA_COLOR, KILL_COLOR, PageRenderer, Where
from deckbar_daemon.poe.leveling.search import gem_search
from deckbar_daemon.poe.leveling.terms import Options, Page
from deckbar_daemon.poe.leveling.tracker import Tracker

POE1_EXE = rb"Z:\home\x\.local\share\Steam\steamapps\common\Path of Exile\PathOfExileSteam.exe" + b"\0--x\0"
POE2_EXE = rb"Z:\games\Path of Exile 2\PathOfExileSteam.exe" + b"\0"
ZONE = '2026/11/18 20:49:39 4433661 1186a803 [DEBUG Client 308] Generating level 2 area "1_1_2" with seed 27'
LEVEL = "2026/11/18 20:52:28 4602289 cffb06be [INFO Client 308] : Hero (Marauder) is now level 3"


def build(char_class: str, *gems: tuple[str, bool]) -> pob.PobBuild:
    group = pob.GemGroup(gems=[pob.Gem(name=name, support=support) for name, support in gems])
    return pob.PobBuild(char_class=char_class, skill_sets=[pob.SkillSet(groups=[group])])


# ---------------------------------------------------------------- Spiel und Client.txt
def test_games_told_apart_by_install_folder():
    assert POE1.install_of(POE1_EXE).install == Path("/home/x/.local/share/Steam/steamapps/common/Path of Exile")
    assert POE2.install_of(POE1_EXE) is None
    assert POE2.install_of(POE2_EXE).install == Path("/games/Path of Exile 2")
    assert POE1.install_of(rb"C:\Path of Exile\PathOfExile.exe").install is None  # im Prefix: Pfad unbekannt
    assert POE1.install_of(rb"Z:\Path of Exile\launcher.exe") is None
    assert linux_path(PureWindowsPath(r"Z:\a\b")) == Path("/a/b")


def test_find_in_proc_and_steam_libraries(tmp_path):
    proc = tmp_path / "proc"
    (proc / "42").mkdir(parents=True)
    (proc / "42" / "comm").write_text("PathOfExileStea\n")
    (proc / "42" / "cmdline").write_bytes(POE1_EXE)
    assert POE1.find(proc) is not None and POE2.find(proc) is None
    steam = tmp_path / ".local/share/Steam/steamapps"
    steam.mkdir(parents=True)
    (steam / "libraryfolders.vdf").write_text(f'"0" {{ "path" "{tmp_path}/lib" }}')
    logs = tmp_path / "lib/steamapps/common/Path of Exile 2/logs"
    logs.mkdir(parents=True)
    (logs / "Client.txt").write_text("")
    assert steam_libraries(tmp_path) == [tmp_path / "lib"]
    assert POE2.steam_client_txt(tmp_path) == logs / "Client.txt" and POE1.steam_client_txt(tmp_path) is None


def test_parse_lines():
    assert parse_line(ZONE) == ZoneEntered("1_1_2", 2)
    assert parse_line(LEVEL) == LevelUp("Hero", "Marauder", 3)
    assert parse_line("[INFO Client 308] Hero: is now level 3 (chat)") is None


def test_client_log_reads_only_new_complete_lines(tmp_path):
    path = tmp_path / "Client.txt"
    path.write_text(f"{LEVEL}\n{ZONE}\nfoo\n")
    log = ClientLog(path)
    assert log.open() == [LevelUp("Hero", "Marauder", 3, live=False), ZoneEntered("1_1_2", 2, live=False)]
    with path.open("a") as f:
        f.write(ZONE.replace("1_1_2", "1_1_3"))  # noch ohne Zeilenende
    assert log.read_new() == []
    with path.open("a") as f:
        f.write("\n")
    assert log.read_new() == [ZoneEntered("1_1_3", 2)]
    path.write_text(f"{ZONE}\n")  # Spiel hat die Datei neu angelegt
    assert log.read_new() == [ZoneEntered("1_1_2", 2)]


# ---------------------------------------------------------------- Guide
def test_build_gems_become_rewards_and_purchases():
    guide = GuideBuilder(load(), Options(), build("witch", ("frostblink", False), ("added fire damage", True)),
                         {}).build(default_guide())
    lines = [line for page in guide.pages for line in page.lines]
    assert any("take:" in line and "frostblink" in line for line in lines) or "buy gem: frostblink" in lines
    assert any(line.startswith("buy gem: added fire damage support") for line in lines)
    assert guide.gems_left == []
    plain = GuideBuilder(load(), Options(), None, {}).build(default_guide())
    assert not any("take:" in line for page in plain.pages for line in page.lines)


def test_league_start_and_bandit_conditions():
    pages = [Page(["a areaid1_1_2"], ["league-start", "yes"]), Page(["b areaid1_1_3"], ["bandit", ["alira"]])]
    assert [p.applies(Options()) for p in pages] == [False, False]
    assert [p.applies(Options(league_start=True, bandit="alira")) for p in pages] == [True, True]


def test_tracker_advances_on_target_zone_after_grace():
    now = [100.0]
    pages = [Page(["kill hillock", "enter areaid1_1_town ;; town"]), Page(["enter areaid1_1_2"]),
             Page(["enter areaid1_1_3"])]
    t = Tracker(pages, Options(), clock=lambda: now[0])
    assert t.target_area == "1_1_town" and t.lines[-1] == "enter areaid1_1_town"
    assert not t.entered("1_1_2") and t.entered("1_1_town") and t.progress == 1
    assert not t.entered("1_1_2")  # zu kurz nach dem letzten Schritt
    now[0] += 3
    assert t.entered("1_1_2") and t.progress == 2 and not t.next()
    assert t.back() and t.progress == 1
    t.reset()
    assert t.skip_to("1_1_3") and t.progress == 2 and not t.skip_to("1_1_9")


def test_render_colors_and_device_markup():
    lines = ["kill hillock", "(img:waypoint) to areaid1_2_town", "(hint)__ (color:0077FF)fireball"]
    out = PageRenderer(load(), Options(), set()).render(lines, Where(act=1))
    kill, area = out.lines[0].segments[1], out.lines[1].segments[-1]
    assert (kill.text, kill.color) == ("hillock", KILL_COLOR)
    assert area.color == AREA_COLOR and area.text.startswith("A2 | ")
    assert [line.bullet for line in out.lines] == ["step", "step", "hint"]
    assert device_line(out.lines[1]).startswith("• #8AB3FF WP# to #FEC076 A2 | ")
    buy = PageRenderer(load(), Options(), set()).render(["talk", "buy gem: frostblink", "go"], Where())
    assert [s.text for s in buy.lines[1].segments] == ["buy gems: ", "frostblink"] and buy.buy_gems == ["frostblink"]


def test_pob_code_and_pobbin():
    xml = ('<PathOfBuilding><Build className="Witch" bandit="Alira"/><Tree><Spec ascendClassId="2"/></Tree>'
           '<Skills><SkillSet title="^xFF0000Early"><Skill label="main"><Gem nameSpec="Vaal Fireball"/>'
           '<Gem nameSpec="Added Fire Damage" gemId="Metadata/Items/Gems/SupportGemAddedFire"'
           ' skillId="SupportAddedFireDamage"/></Skill></SkillSet></Skills></PathOfBuilding>')
    code = base64.urlsafe_b64encode(zlib.compress(xml.encode())).decode()
    b = pob.parse(pob.decode(code), set(load().gems))
    assert (b.char_class, b.ascendancies, b.bandit) == ("witch", ["elementalist"], "alira")
    assert b.skill_sets[0].title == "early"
    assert [g.key for g in b.skill_sets[0].groups[0].gems] == ["fireball", "added fire damage support"]
    assert pob.is_pobbin("https://pobb.in/AbC-12") and pob.pobbin_raw_url("pobb.in/x") == "https://pobb.in/x/raw"
    try:
        pob.decode("kein code")
    except pob.PobError:
        pass
    else:
        raise AssertionError("ungültiger Code muss PobError werfen")


def test_experience_and_vendor_search():
    assert experience(10, 10).text() == "100 %" and experience(10, 30).percent < 50
    assert experience(10, 30, in_town=True).percent == 100
    xp = experience(32, 20)
    assert (xp.low, xp.high) == (27, 37)
    chunks = gem_search([f"gem number {i}" for i in range(40)], load())
    assert len(chunks) > 1 and all(len(c) <= 250 and c.startswith("^(") for c in chunks)


async def test_session_reads_last_state_without_game(tmp_path):
    from nexcore import EventBus

    from deckbar_daemon.core.topics import POE_LOG
    from deckbar_daemon.poe.session import PoeSession

    path = tmp_path / "Client.txt"
    path.write_text(f"{LEVEL}\n{ZONE}\n")
    bus = EventBus()
    seen = []
    bus.on(POE_LOG, seen.append)
    session = PoeSession(bus, POE1, lambda: str(path))
    await session._follow()
    assert session.zone == ZoneEntered("1_1_2", 2, live=False) and "Hero" in session.levels
    assert [m.event for m in seen] == [LevelUp("Hero", "Marauder", 3, live=False), session.zone]
