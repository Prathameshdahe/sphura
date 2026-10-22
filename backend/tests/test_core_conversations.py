from __future__ import annotations

from tests.test_core_chat import first, send


def _new(client, user, content: str) -> str:
    _, events = send(client, user, content=content)
    return first(events, "start")["conversationId"]


def test_conversation_crud_and_ordering(client, user):
    a = _new(client, user, "Quantum tunnelling basics")
    b = _new(client, user, "Banana bread recipe")
    listed = client.get("/api/conversations", headers=user["headers"]).json()
    assert [c["id"] for c in listed][:2] == [b, a]  # newest first
    assert set(listed[0]) == {"id", "title", "mode", "pinned", "createdAt", "updatedAt"}

    r = client.patch(f"/api/conversations/{a}", json={"pinned": True}, headers=user["headers"])
    assert r.status_code == 200 and r.json()["pinned"] is True
    listed = client.get("/api/conversations", headers=user["headers"]).json()
    assert listed[0]["id"] == a  # pinned first

    r = client.patch(f"/api/conversations/{a}", json={"title": "  Physics   notes "}, headers=user["headers"])
    assert r.json()["title"] == "Physics notes"
    assert client.patch(f"/api/conversations/{a}", json={"title": ""}, headers=user["headers"]).status_code == 422

    detail = client.get(f"/api/conversations/{a}", headers=user["headers"]).json()
    assert detail["conversation"]["title"] == "Physics notes"
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]

    assert client.delete(f"/api/conversations/{b}", headers=user["headers"]).status_code == 204
    assert client.get(f"/api/conversations/{b}", headers=user["headers"]).status_code == 404
    assert b not in {c["id"] for c in client.get("/api/conversations", headers=user["headers"]).json()}


def test_search_by_title_and_content(client, user):
    a = _new(client, user, "Photosynthesis in desert plants")
    b = _new(client, user, "Something unrelated entirely")
    client.patch(f"/api/conversations/{b}", json={"title": "Zebra facts"}, headers=user["headers"])

    def search(q: str) -> set[str]:
        r = client.get("/api/conversations", params={"q": q}, headers=user["headers"])
        assert r.status_code == 200
        return {c["id"] for c in r.json()}

    assert search("zebra") == {b}
    assert search("DESERT plants") == {a}           # matches message content, case-insensitive
    assert search("100%_literal") == set()           # LIKE wildcards are escaped
    assert search("") >= {a, b}


def test_cross_user_isolation(client, user, other_user):
    cid = _new(client, user, "Private thoughts")
    h = other_user["headers"]
    assert client.get(f"/api/conversations/{cid}", headers=h).status_code == 404
    assert client.patch(f"/api/conversations/{cid}", json={"pinned": True}, headers=h).status_code == 404
    assert client.delete(f"/api/conversations/{cid}", headers=h).status_code == 404
    assert cid not in {c["id"] for c in client.get("/api/conversations", headers=h).json()}
    r = client.get(f"/api/conversations/{cid}", headers=h)
    assert r.json() == {"detail": "Conversation not found"}
    assert client.get("/api/conversations").status_code == 401
