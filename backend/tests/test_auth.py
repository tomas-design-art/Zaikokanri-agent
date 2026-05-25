"""Auth endpoints のテスト。"""
from __future__ import annotations


def test_login_success(client):
    r = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "ADMIN"
    # httpOnly cookies がセットされる
    cookies = {c.name: c for c in client.cookies.jar}
    assert "zk_access" in cookies
    assert "zk_refresh" in cookies


def test_login_wrong_password(client):
    r = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user(client):
    r = client.post("/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401


def test_me_requires_auth(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_after_login(admin_client):
    r = admin_client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


def test_logout_clears_cookies(admin_client):
    r = admin_client.post("/auth/logout")
    assert r.status_code == 200
    # ログアウト後は /me が401
    r2 = admin_client.get("/auth/me")
    assert r2.status_code == 401
