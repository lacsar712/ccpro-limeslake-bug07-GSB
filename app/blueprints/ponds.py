from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Plant, Pond
from app.services.rules import RuleError, assert_can_set_pond_status

bp = Blueprint("ponds", __name__, url_prefix="/ponds")

STATUS_LABELS = {
    Pond.STATUS_FILLING: "注水中",
    Pond.STATUS_SLAKING: "熟化中",
    Pond.STATUS_DRAWN: "已出灰",
}


@bp.route("/")
@login_required
def list_ponds():
    ponds = Pond.query.join(Plant).order_by(Plant.name, Pond.code).all()
    plants = Plant.query.order_by(Plant.name).all()
    return render_template(
        "ponds/list.html",
        ponds=ponds,
        plants=plants,
        status_labels=STATUS_LABELS,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create_pond():
    plants = Plant.query.order_by(Plant.name).all()
    if request.method == "POST":
        plant_id_raw = request.form.get("plant_id", "")
        code = (request.form.get("code") or "").strip()
        status = request.form.get("status") or Pond.STATUS_FILLING
        try:
            capacity = float(request.form.get("capacity_m3") or 0)
        except ValueError:
            capacity = 0.0
        notes = (request.form.get("notes") or "").strip()

        plant = db.session.get(Plant, int(plant_id_raw)) if plant_id_raw.isdigit() else None
        if plant is None:
            flash("请选择有效厂区", "error")
            return render_template(
                "ponds/form.html",
                pond=None,
                plants=plants,
                status_labels=STATUS_LABELS,
            )
        if not code:
            flash("池编号不能为空", "error")
            return render_template(
                "ponds/form.html",
                pond=None,
                plants=plants,
                status_labels=STATUS_LABELS,
            )

        if status == Pond.STATUS_DRAWN:
            status = Pond.STATUS_FILLING

        # 先查一次给出友好提示；真正的唯一性由 uq_pond_code_per_plant 约束兜底，
        # 两人几乎同时提交同厂同号时，数据库只放行一笔，另一笔在下方
        # IntegrityError 处回滚并报错——绝不允许覆盖已有池。
        if Pond.query.filter_by(plant_id=plant.id, code=code).first():
            flash(f"厂区 {plant.name} 已存在编号为 {code} 的熟化池，不能重复创建", "error")
            return render_template(
                "ponds/form.html",
                pond=None,
                plants=plants,
                status_labels=STATUS_LABELS,
            )

        pond = Pond(
            plant_id=plant.id,
            code=code,
            status=status,
            capacity_m3=capacity,
            notes=notes,
        )
        if request.form.get("status") == Pond.STATUS_DRAWN:
            flash("新建池不能直接设为已出灰，已改为注水中", "error")
        db.session.add(pond)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(f"厂区 {plant.name} 已存在编号为 {code} 的熟化池，不能重复创建", "error")
            return render_template(
                "ponds/form.html",
                pond=None,
                plants=Plant.query.order_by(Plant.name).all(),
                status_labels=STATUS_LABELS,
            )
        flash("熟化池已创建", "ok")
        return redirect(url_for("board.floor_plan", plant_id=plant.id, pond=pond.id))
    return render_template(
        "ponds/form.html",
        pond=None,
        plants=plants,
        status_labels=STATUS_LABELS,
    )


@bp.route("/<int:pond_id>/edit", methods=["GET", "POST"])
@login_required
def edit_pond(pond_id: int):
    pond = db.session.get(Pond, pond_id)
    if pond is None:
        flash("熟化池不存在或已随厂区删除", "error")
        return redirect(url_for("ponds.list_ponds"))
    plants = Plant.query.order_by(Plant.name).all()
    if request.method == "POST":
        plant_id_raw = request.form.get("plant_id", "")
        code = (request.form.get("code") or "").strip()
        status = request.form.get("status") or pond.status
        try:
            capacity = float(request.form.get("capacity_m3") or 0)
        except ValueError:
            capacity = 0.0
        notes = (request.form.get("notes") or "").strip()
        plant = db.session.get(Plant, int(plant_id_raw)) if plant_id_raw.isdigit() else None
        if plant is None:
            flash("请选择有效厂区", "error")
        elif not code:
            flash("池编号不能为空", "error")
        else:
            dup = Pond.query.filter(
                Pond.plant_id == plant.id,
                Pond.code == code,
                Pond.id != pond.id,
            ).first()
            if dup:
                flash("同一厂区内池编号必须唯一", "error")
            else:
                try:
                    assert_can_set_pond_status(pond, status)
                    pond.plant_id = plant.id
                    pond.code = code
                    pond.status = status
                    pond.capacity_m3 = capacity
                    pond.notes = notes
                    db.session.commit()
                    flash("熟化池已更新", "ok")
                    return redirect(url_for("board.floor_plan", plant_id=plant.id, pond=pond.id))
                except RuleError as exc:
                    db.session.rollback()
                    flash(str(exc), "error")
                except IntegrityError:
                    db.session.rollback()
                    flash("同一厂区内池编号必须唯一", "error")
    return render_template(
        "ponds/form.html",
        pond=pond,
        plants=Plant.query.order_by(Plant.name).all(),
        status_labels=STATUS_LABELS,
    )
