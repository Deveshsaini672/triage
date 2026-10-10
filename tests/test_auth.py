from tests.conftest import PASSWORD


def test_login_ok_and_me(client, auth):
    h = auth("billing@example.com")
    r = client.get("/auth/me", headers=h)
    assert r.status_code == 200
    assert r.json()["email"] == "billing@example.com"


def test_login_wrong_password_and_unknown_email(client):
    for user in ("billing@example.com", "nobody@example.com"):
        r = client.post("/auth/login", data={"username": user, "password": "wrong"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Incorrect email or password"


def test_garbage_token_rejected(client):
    r = client.get("/tickets", headers={"Authorization": "Bearer abc"})
    assert r.status_code == 401


def test_no_token_rejected(client):
    assert client.get("/tickets").status_code == 401
