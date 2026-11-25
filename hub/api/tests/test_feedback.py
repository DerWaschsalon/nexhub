"""Feedback-Board: schreiben, abstimmen, Status nur von Admins, anonym für andere Mitglieder."""
from nexhub_api.modules.feedback import routes as feedback

from .conftest import ADMIN, MEMBER
from .test_devices import ORIGIN


def add(client, title="Mehr Dungeons auswerten", body=""):
    return client.post("/api/feedback", json={"title": title, "body": body}, headers=ORIGIN)


def test_schreiben_und_abstimmen(as_user):
    member, admin = as_user(MEMBER), as_user(ADMIN)
    entry = add(member, body="Auch Transzendenz.").json()
    assert (entry["status"], entry["votes"], entry["voted"], entry["mine"]) == ("neu", 1, True, True)
    assert entry["author"] is None  # Mitglieder sehen keine Namen

    seen = admin.get("/api/feedback").json()[0]
    assert (seen["votes"], seen["voted"], seen["mine"], seen["author"]) == (1, False, False, "Testname")
    # eine Stimme je Konto, auch bei zweimal Klicken; zurücknehmen geht
    for _ in range(2):
        assert admin.post(f"/api/feedback/{entry['id']}/vote", headers=ORIGIN).json()["votes"] == 2
    assert admin.delete(f"/api/feedback/{entry['id']}/vote", headers=ORIGIN).json()["votes"] == 1


def test_meiste_stimmen_zuerst(as_user):
    member, admin = as_user(MEMBER), as_user(ADMIN)
    first, second = add(member, "Erster Wunsch").json(), add(member, "Zweiter Wunsch").json()
    admin.post(f"/api/feedback/{first['id']}/vote", headers=ORIGIN)
    assert [e["id"] for e in member.get("/api/feedback").json()] == [first["id"], second["id"]]


def test_status_und_loeschen_nur_admins(as_user):
    member, admin = as_user(MEMBER), as_user(ADMIN)
    entry = add(member).json()
    path = f"/api/admin/feedback/{entry['id']}"
    assert member.put(path, json={"status": "geplant"}, headers=ORIGIN).status_code == 403
    assert admin.put(path, json={"status": "geplant"}, headers=ORIGIN).json()["status"] == "geplant"
    assert admin.put(path, json={"status": "fertig"}, headers=ORIGIN).status_code == 422
    assert member.delete(path, headers=ORIGIN).status_code == 403
    assert admin.delete(path, headers=ORIGIN).status_code == 204 and member.get("/api/feedback").json() == []


def test_grenze_je_tag_und_pflichtfelder(as_user, monkeypatch):
    monkeypatch.setattr(feedback, "PER_DAY", 2)
    member = as_user(MEMBER)
    assert add(member, "x").status_code == 422  # zu kurz
    assert [add(member, f"Wunsch {n}").status_code for n in range(3)] == [201, 201, 429]


def test_nur_mit_login(client):
    assert client.get("/api/feedback").status_code == 401
