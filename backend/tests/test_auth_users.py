"""認証・ユーザー管理（受け入れ条件 A-01〜A-08）。"""
from __future__ import annotations

from app.models import User


def test_A01_refresh_issues_new_access_cookie(make_client):
    c = make_client("taro")
    # アクセストークンだけ消しても、リフレッシュで復帰できる
    c.cookies.delete("zk_access")
    assert c.get("/auth/me").status_code == 401
    r = c.post("/auth/refresh")
    assert r.status_code == 200, r.text
    assert c.get("/auth/me").status_code == 200


def test_A01_refresh_rejects_access_token_as_refresh(make_client):
    c = make_client("taro")
    access = c.cookies.get("zk_access")
    c.cookies.clear()
    c.cookies.set("zk_refresh", access)
    assert c.post("/auth/refresh").status_code == 401


def test_A02_admin_cannot_deactivate_self(admin_client, db):
    me = admin_client.get("/auth/me").json()
    r = admin_client.delete(f"/users/{me['id']}")
    assert r.status_code == 400
    assert "自分" in r.json()["detail"]


def test_A02_admin_cannot_demote_self(admin_client):
    me = admin_client.get("/auth/me").json()
    r = admin_client.patch(f"/users/{me['id']}", json={"user_role": "USER"})
    assert r.status_code == 400


def test_A02_last_admin_cannot_be_removed(make_client, db):
    # 2人目の管理者を作り、その人から最初の管理者を降格 → OK（まだ1人残る）
    admin = make_client("admin")
    r = admin.post(
        "/users",
        json={"username": "boss", "password": "bosspass1", "display_name": "部長", "user_role": "ADMIN"},
    )
    assert r.status_code == 201, r.text
    boss_id = r.json()["id"]
    db.query(User).filter(User.id == boss_id).update({"must_change_password": 0})
    db.commit()
    boss = make_client(None)
    boss.post("/auth/login", json={"username": "boss", "password": "bosspass1"})
    first_admin_id = admin.get("/auth/me").json()["id"]
    assert boss.patch(f"/users/{first_admin_id}", json={"user_role": "USER"}).status_code == 200
    # 残った管理者（boss）は自分を無効化できない＝管理者0人にはならない
    assert boss.delete(f"/users/{boss_id}").status_code == 400


def test_A03_created_user_must_change_password(admin_client, make_client):
    r = admin_client.post(
        "/users",
        json={"username": "newbie", "password": "temppass1", "display_name": "新人", "user_role": "USER"},
    )
    assert r.status_code == 201, r.text
    c = make_client(None)
    login = c.post("/auth/login", json={"username": "newbie", "password": "temppass1"})
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True
    # 変更するまで業務APIは使えない
    blocked = c.get("/inventory")
    assert blocked.status_code == 403
    assert "パスワード" in blocked.json()["detail"]
    # /auth/me は使える
    assert c.get("/auth/me").status_code == 200
    ch = c.post("/auth/password", json={"current_password": "temppass1", "new_password": "mynewpass1"})
    assert ch.status_code == 200, ch.text
    assert c.get("/inventory").status_code == 200
    assert c.get("/auth/me").json()["must_change_password"] is False


def test_A04_change_password_requires_current(user_client):
    r = user_client.post("/auth/password", json={"current_password": "wrong", "new_password": "abcdefgh1"})
    assert r.status_code == 400
    ok = user_client.post("/auth/password", json={"current_password": "user1234", "new_password": "abcdefgh1"})
    assert ok.status_code == 200


def test_A05_admin_can_reset_and_reactivate(admin_client, db):
    taro = db.query(User).filter(User.username == "taro").one()
    assert admin_client.patch(f"/users/{taro.id}", json={"password": "resetpass1"}).status_code == 200
    db.expire_all()
    assert db.get(User, taro.id).must_change_password == 1
    assert admin_client.delete(f"/users/{taro.id}").status_code == 204
    users = admin_client.get("/users", params={"include_inactive": True}).json()
    assert any(u["username"] == "taro" and u["is_active"] == 0 for u in users)
    assert admin_client.patch(f"/users/{taro.id}", json={"is_active": 1}).status_code == 200


def test_A06_password_min_length_8(admin_client):
    r = admin_client.post(
        "/users",
        json={"username": "short", "password": "abc1234", "display_name": "短い", "user_role": "USER"},
    )
    assert r.status_code == 422
    assert "8" in r.json()["detail"]


def test_A08_jwt_library_is_pyjwt():
    from pathlib import Path

    import app.auth.jwt as jwt_mod

    assert "jose" not in Path(jwt_mod.__file__).read_text(encoding="utf-8")


def test_login_response_and_cookie_flags(client):
    r = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    body = r.json()["user"]
    assert body["role"] == "ADMIN"
    assert body["must_change_password"] is False
    set_cookie = r.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie


def test_inactive_user_cannot_login(admin_client, client, db):
    taro = db.query(User).filter(User.username == "taro").one()
    admin_client.delete(f"/users/{taro.id}")
    r = client.post("/auth/login", json={"username": "taro", "password": "user1234"})
    assert r.status_code == 401
