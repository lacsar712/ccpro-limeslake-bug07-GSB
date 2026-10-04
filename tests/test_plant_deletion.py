"""验收一：删除厂区必须级联带走池与批次，且失败整笔回滚。"""

from unittest.mock import patch

from app.extensions import db
from app.models import Plant, Pond, SlakeBatch


def test_delete_plant_cascades_ponds_and_batches(app, client, seeded):
    a, b = seeded["plant_a"], seeded["plant_b"]

    resp = client.post(f"/plants/{a}/delete", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert db.session.get(Plant, a) is None
        # 厂区的池全部消失，不留孤儿池
        assert Pond.query.filter_by(plant_id=a).count() == 0
        # 池上的批次一并消失，不留孤儿班
        assert (
            SlakeBatch.query.filter(
                SlakeBatch.pond_id.in_([seeded["p1"], seeded["p2"]])
            ).count()
            == 0
        )
        # 其它厂区及其池、批次原样保留
        assert db.session.get(Plant, b) is not None
        assert db.session.get(Pond, seeded["q1"]) is not None
        assert SlakeBatch.query.filter_by(pond_id=seeded["q1"]).count() == 1


def test_deleted_plant_invisible_everywhere(app, client, seeded):
    a = seeded["plant_a"]
    client.post(f"/plants/{a}/delete", follow_redirects=True)

    # 厂区列表不再出现
    page = client.get("/plants/").get_data(as_text=True)
    assert "将删厂" not in page
    assert "保留厂" in page

    # 平面图：直连已删厂的 id 也看不到它的池
    board = client.get(f"/board/?plant_id={a}").get_data(as_text=True)
    assert "A-01" not in board
    assert "A-02" not in board
    assert "A厂一号池" not in board
    # 自动落到保留厂，仍能正常显示
    assert "B-01" in board

    # 其它入口：熟化池列表
    ponds_page = client.get("/ponds/").get_data(as_text=True)
    assert "A-01" not in ponds_page
    assert "A-02" not in ponds_page
    assert "B-01" in ponds_page

    # 其它入口：批次列表 / 新建批次下拉
    batches_page = client.get("/batches/").get_data(as_text=True)
    assert "A-01的批次" not in batches_page
    assert "A-02的批次" not in batches_page
    assert "B-01的批次" in batches_page
    batch_form = client.get("/batches/new").get_data(as_text=True)
    assert "A-01" not in batch_form


def test_delete_failure_rolls_back_entirely(app, client, seeded):
    a = seeded["plant_a"]

    # 提交阶段抛错：厂区、池、批次必须全部保持原样
    with patch.object(db.session, "commit", side_effect=RuntimeError("db down")):
        resp = client.post(f"/plants/{a}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert "删除失败" in resp.get_data(as_text=True)

    with app.app_context():
        plant = db.session.get(Plant, a)
        assert plant is not None
        assert Pond.query.filter_by(plant_id=a).count() == 2
        assert (
            SlakeBatch.query.filter(
                SlakeBatch.pond_id.in_([seeded["p1"], seeded["p2"]])
            ).count()
            == 2
        )


def test_delete_missing_plant_404(client):
    assert client.post("/plants/99999/delete").status_code == 404
