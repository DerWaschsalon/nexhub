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


def test_statistik_zaehlt_aus_vorhandenen_tabellen(client, as_user):
    from .test_devices import pair
    from .test_runs import nexlog, upload

    admin = as_user(ADMIN)
    upload(client, pair(client, admin), nexlog())
    s = admin.get("/api/admin/stats", params={"days": 7}).json()
    assert len(s["days"]) == 7 and s["runs"] == [0] * 6 + [1] and s["accounts"][-1] == 1
    assert (s["total_runs"], s["total_accounts"], s["devices"], s["devices_active"]) == (1, 1, 1, 1)
    assert sum(s["devices_by_version"].values()) == 1 and s["bis"] == []
    assert admin.get("/api/admin/stats", params={"days": 3}).status_code == 422
    assert as_user(MEMBER).get("/api/admin/stats").status_code == 403


def test_tagesreihe():
    from datetime import UTC, date, datetime

    from nexhub_api.stats import last_days, per_day

    days = last_days(date(2026, 11, 24), 3)
    assert days == [date(2026, 11, 22), date(2026, 11, 23), date(2026, 11, 24)]
    stamps = [datetime(2026, 11, 22, 23, 59, tzinfo=UTC), datetime(2026, 11, 24, 0, 0, tzinfo=UTC),
              datetime(2026, 11, 24, 12, 0, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)]
    assert per_day(stamps, days) == [1, 0, 2]
