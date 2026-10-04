import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp(prefix="limeslake-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SECRET_KEY"] = "test-secret"

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Plant, Pond, SlakeBatch, User  # noqa: E402


@pytest.fixture()
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with application.app_context():
        db.drop_all()
        db.create_all()
        admin = User(username="admin", role="admin")
        admin.set_password("123456")
        db.session.add(admin)
        db.session.commit()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    c = app.test_client()
    resp = c.post(
        "/auth/login",
        data={"username": "admin", "password": "123456"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    return c


@pytest.fixture()
def seeded(app):
    """厂区A（将被删，含池与批次）+ 厂区B（保留）。"""
    with app.app_context():
        a = Plant(name="将删厂", location="甲地", notes="A厂备注")
        b = Plant(name="保留厂", location="乙地", notes="B厂备注")
        db.session.add_all([a, b])
        db.session.flush()
        p1 = Pond(plant=a, code="A-01", status=Pond.STATUS_SLAKING,
                  capacity_m3=48.0, notes="A厂一号池")
        p2 = Pond(plant=a, code="A-02", status=Pond.STATUS_FILLING,
                  capacity_m3=36.0, notes="A厂二号池")
        q1 = Pond(plant=b, code="B-01", status=Pond.STATUS_FILLING,
                  capacity_m3=30.0, notes="B厂一号池")
        db.session.add_all([p1, p2, q1])
        db.session.flush()
        db.session.add_all([
            SlakeBatch(pond=p1, target_temp_c=85.0, peak_temp_c=72.0,
                       notes="A-01的批次"),
            SlakeBatch(pond=p2, target_temp_c=80.0, peak_temp_c=None,
                       notes="A-02的批次"),
            SlakeBatch(pond=q1, target_temp_c=81.0, peak_temp_c=None,
                       notes="B-01的批次"),
        ])
        db.session.commit()
        return {"plant_a": a.id, "plant_b": b.id,
                "p1": p1.id, "p2": p2.id, "q1": q1.id}
