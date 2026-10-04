"""验收二：同厂同号池必须挡下、不得覆盖；并发下只许一笔入库。"""

import threading

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Plant, Pond


def _create_pond(client, plant_id, code, **overrides):
    data = {
        "plant_id": plant_id,
        "code": code,
        "status": "filling",
        "capacity_m3": "40",
        "notes": "",
    }
    data.update(overrides)
    return client.post("/ponds/new", data=data, follow_redirects=True)


def test_create_pond_ok(app, client, seeded):
    b = seeded["plant_b"]
    resp = _create_pond(client, b, "B-02", capacity_m3="33.5", notes="新池")
    assert resp.status_code == 200
    with app.app_context():
        pond = Pond.query.filter_by(plant_id=b, code="B-02").one()
        assert pond.capacity_m3 == 33.5
        assert pond.notes == "新池"


def test_duplicate_code_rejected_and_never_overwrites(app, client, seeded):
    a = seeded["plant_a"]
    original = seeded["p1"]

    # 用完全不同的容量/备注/状态去撞已有编号 A-01
    resp = _create_pond(
        client, a, "A-01",
        status="slaking", capacity_m3="999", notes="恶意覆盖",
    )
    page = resp.get_data(as_text=True)
    assert "不能重复创建" in page
    # 应当留在表单页（200），而不是跳转平面图当成功
    assert resp.status_code == 200

    with app.app_context():
        # 仍是同一行，字段一字未改
        assert Pond.query.filter_by(plant_id=a, code="A-01").count() == 1
        pond = db.session.get(Pond, original)
        assert pond.capacity_m3 == 48.0
        assert pond.notes == "A厂一号池"
        assert pond.status == Pond.STATUS_SLAKING


def test_same_code_allowed_in_different_plant(app, client, seeded):
    a, b = seeded["plant_a"], seeded["plant_b"]
    resp = _create_pond(client, b, "A-01", capacity_m3="20")
    assert resp.status_code == 200
    with app.app_context():
        assert Pond.query.filter_by(code="A-01").count() == 2
        assert db.session.get(Pond, seeded["p1"]).plant_id == a
        assert Pond.query.filter_by(plant_id=b, code="A-01").count() == 1


def test_create_with_empty_code_rejected(app, client, seeded):
    b = seeded["plant_b"]
    resp = _create_pond(client, b, "   ")
    assert "池编号不能为空" in resp.get_data(as_text=True)
    with app.app_context():
        assert Pond.query.filter_by(plant_id=b).count() == 1


def test_create_with_missing_plant_rejected(app, client, seeded):
    resp = _create_pond(client, 99999, "X-09")
    assert "厂区不存在或已删除" in resp.get_data(as_text=True)
    with app.app_context():
        assert Pond.query.filter_by(code="X-09").count() == 0


def test_new_pond_cannot_start_drawn(app, client, seeded):
    b = seeded["plant_b"]
    _create_pond(client, b, "B-03", status="drawn")
    with app.app_context():
        pond = Pond.query.filter_by(plant_id=b, code="B-03").one()
        assert pond.status == Pond.STATUS_FILLING


def test_integrity_error_on_commit_is_handled(app, client, seeded, monkeypatch):
    """模拟并发：预检通过后、提交时唯一约束报错——必须回滚并提示，会话仍可用。"""
    b = seeded["plant_b"]
    boom = IntegrityError("INSERT INTO ponds ...", {}, Exception("unique violation"))

    def raise_boom(*args, **kwargs):
        raise boom

    monkeypatch.setattr(db.session, "commit", raise_boom)

    resp = _create_pond(client, b, "B-02", capacity_m3="33")
    assert "不能重复创建" in resp.get_data(as_text=True)
    assert resp.status_code == 200

    monkeypatch.undo()
    # 回滚后会话未污染：后续正常请求仍可成功
    resp2 = _create_pond(client, b, "B-02", capacity_m3="33")
    assert resp2.status_code == 200
    with app.app_context():
        assert Pond.query.filter_by(plant_id=b, code="B-02").count() == 1


def test_database_constraint_allows_only_one_duplicate(app, seeded):
    """数据层保证：绕过应用直接并发插同厂同号，只有一笔能落库。"""
    a = seeded["plant_a"]
    results = []

    def insert():
        with app.app_context():
            engine = db.engine
            with engine.connect() as conn:
                from sqlalchemy import text
                try:
                    conn.execute(
                        text(
                            "INSERT INTO ponds (plant_id, code, status,"
                            " capacity_m3, notes) VALUES (:p, 'A-99',"
                            " 'filling', 10.0, '')"
                        ),
                        {"p": a},
                    )
                    conn.commit()
                    results.append("ok")
                except IntegrityError:
                    conn.rollback()
                    results.append("dup")

    threads = [threading.Thread(target=insert) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == ["dup", "ok"]
    with app.app_context():
        assert Pond.query.filter_by(plant_id=a, code="A-99").count() == 1
