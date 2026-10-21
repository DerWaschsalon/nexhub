from alembic.script import ScriptDirectory

from nexhub_api.db import alembic_config

from .conftest import ADMIN, BASE, MEMBER, log_in

ORIGIN = {"origin": BASE}


def _account(admin, discord_id: int) -> dict:
    return next(a for a in admin.get("/api/admin/users").json() if a["discord_id"] == str(discord_id))


def test_admin_bereich_nur_fuer_admins(client, as_user):
    assert client.get("/api/admin/users").status_code == 401
    member = as_user(MEMBER)
    assert member.get("/api/admin/users").status_code == 403
    assert member.get("/api/admin/status").status_code == 403
    assert as_user(ADMIN).get("/api/admin/users").status_code == 200


def test_kontenliste(as_user):
    as_user(MEMBER)
    admin = as_user(ADMIN)
    accounts = admin.get("/api/admin/users").json()
    assert [a["role"] for a in accounts] == ["admin", "member"]  # zuletzt angemeldet zuerst
    assert _account(admin, MEMBER)["sessions"] == 1
    assert _account(admin, MEMBER)["blocked"] is False


def test_status(as_user):
    s = as_user(ADMIN).get("/api/admin/status").json()
    head = ScriptDirectory.from_config(alembic_config("")).get_current_head()
    assert s["db_revision"] == head and s["login"] is True and s["member_check"] is True
    assert s["accounts"] == 1 and s["active_sessions"] == 1


def test_konto_abmelden(as_user):
    member = as_user(MEMBER)
    admin = as_user(ADMIN)
    target = _account(admin, MEMBER)["id"]
    assert admin.post(f"/api/admin/users/{target}/logout", headers=ORIGIN).status_code == 204
    assert member.get("/api/me").status_code == 401
    assert admin.post("/api/admin/users/9999/logout", headers=ORIGIN).status_code == 404


def test_sperren_und_entsperren(as_user, make_client, fake):
    member = as_user(MEMBER)
    admin = as_user(ADMIN)
    target = _account(admin, MEMBER)["id"]

    assert admin.post(f"/api/admin/users/{target}/block", headers=ORIGIN).status_code == 204
    assert member.get("/api/me").status_code == 401
    assert _account(admin, MEMBER)["blocked"] is True
    with make_client() as again:
        fake.user = MEMBER
        assert log_in(again).headers["location"] == "/login?fehler=gesperrt"

    assert admin.post(f"/api/admin/users/{target}/unblock", headers=ORIGIN).status_code == 204
    with make_client() as again:
        fake.user = MEMBER
        log_in(again)
        assert again.get("/api/me").status_code == 200


def test_admins_lassen_sich_nicht_sperren(as_user):
    admin = as_user(ADMIN)
    me = _account(admin, ADMIN)["id"]
    assert admin.post(f"/api/admin/users/{me}/block", headers=ORIGIN).status_code == 400
