import uuid
from types import SimpleNamespace

import app.api.tickets as tickets_api

KEY = {"X-API-Key": "test-key"}


class Recorder:
    def __init__(self):
        self.ids = []

    def delay(self, ticket_id):
        self.ids.append(ticket_id)


def test_ingest_requires_api_key(client):
    body = {"subject": "s", "body": "b"}
    assert client.post("/tickets", json=body).status_code == 401
    assert client.post("/tickets", json=body, headers={"X-API-Key": "bad"}).status_code == 401


def test_ingest_validation(client):
    r = client.post("/tickets", json={"subject": "", "body": "b"}, headers=KEY)
    assert r.status_code == 422


def test_ingest_creates_pending_and_enqueues(client, monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(tickets_api, "classify_ticket", rec)
    r = client.post("/tickets", json={"subject": "Hi", "body": "Help"}, headers=KEY)
    assert r.status_code == 202
    assert r.json()["status"] == "pending"
    assert rec.ids == [r.json()["id"]]


def test_ingest_survives_broker_outage(client, monkeypatch):
    class Boom:
        def delay(self, _):
            raise ConnectionError("broker down")

    monkeypatch.setattr(tickets_api, "classify_ticket", Boom())
    r = client.post("/tickets", json={"subject": "Hi", "body": "Help"}, headers=KEY)
    assert r.status_code == 202  # ticket is saved; the sweeper will pick it up


def test_list_is_team_scoped(client, auth, make_ticket, seeded):
    mine = make_ticket(team_id=seeded["Billing"])
    make_ticket(team_id=seeded["Technical"])
    make_ticket(team_id=None)  # still pending: nobody sees it

    r = client.get("/tickets", headers=auth("billing@example.com"))
    assert [t["id"] for t in r.json()] == [str(mine.id)]
    assert client.get("/tickets", headers=auth("tech@example.com")).json() != []


def test_get_ticket_other_team_is_indistinguishable_from_missing(client, auth, make_ticket, seeded):
    t = make_ticket(team_id=seeded["Billing"])
    ok = client.get(f"/tickets/{t.id}", headers=auth("billing@example.com"))
    assert ok.status_code == 200

    other = client.get(f"/tickets/{t.id}", headers=auth("tech@example.com"))
    missing = client.get(f"/tickets/{uuid.uuid4()}", headers=auth("tech@example.com"))
    assert other.status_code == missing.status_code == 404
    assert other.json() == missing.json()


def test_reassign_moves_ticket_and_records_history(client, auth, make_ticket, seeded):
    t = make_ticket(team_id=seeded["Triage"])
    h = auth("triage@example.com")

    r = client.patch(f"/tickets/{t.id}/reassign", json={"team_id": seeded["Technical"]}, headers=h)
    assert r.status_code == 200
    hist = r.json()["routing_history"]
    assert hist[-1]["reason"] == "manual"
    assert hist[-1]["from_team_id"] == seeded["Triage"]
    assert hist[-1]["to_team_id"] == seeded["Technical"]
    assert hist[-1]["actor_agent_id"] is not None

    # Triage no longer sees it; Technical now does.
    assert client.get(f"/tickets/{t.id}", headers=h).status_code == 404
    assert client.get(f"/tickets/{t.id}", headers=auth("tech@example.com")).status_code == 200


def test_reassign_rules(client, auth, make_ticket, seeded):
    t = make_ticket(team_id=seeded["Billing"])
    h = auth("billing@example.com")
    same = client.patch(f"/tickets/{t.id}/reassign", json={"team_id": seeded["Billing"]}, headers=h)
    assert same.status_code == 409
    nope = client.patch(f"/tickets/{t.id}/reassign", json={"team_id": 9999}, headers=h)
    assert nope.status_code == 404
    # Can't touch another team's ticket
    foreign = client.patch(
        f"/tickets/{t.id}/reassign", json={"team_id": seeded["General"]},
        headers=auth("tech@example.com"),
    )
    assert foreign.status_code == 404


def test_teams_endpoint(client, auth):
    r = client.get("/teams", headers=auth("billing@example.com"))
    assert {t["name"] for t in r.json()} == {"Billing", "Technical", "General", "Triage"}
