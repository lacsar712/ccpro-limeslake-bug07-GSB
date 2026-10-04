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
        plant_id_raw = (request.form.get("plant_id") or "").strip()
        code = (request.form.get("code") or "").strip()
        status = request.form.get("status") or Pond.STATUS_FILLING
        notes = (request.form.get("notes") or "").strip()
        try:
            plant_id = int(plant_id_raw)
            capacity = float(request.form.get("capacity_m3") or 0)
        except ValueError:
            flash("厂区或容量格式无效", "error")
            return render_template(
                "ponds/form.html",
                pond=None,
                plants=plants,
                status_labels=STATUS_LABELS,
            )

        plant = db.session.get(Plant, plant_id)
        if plant is None:
            flash("所选厂区不存在或已删除，请重新选择", "error")
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
        plant_name = plant.name

        # 同厂同号必须挡下：只报错，绝不覆盖已有池的任何字段。
        existing = Pond.query.filter_by(plant_id=plant_id, code=code).first()
        if existing is not None:
            flash(f"厂区 {plant_name} 已存在同编号池 {code}，不能重复创建", "error")
            return render_template(
                "ponds/form.html",
                pond=None,
                plants=plants,
                status_labels=STATUS_LABELS,
            )

        initial_status = status
        if status not in Pond.STATUS_CHOICES or status == Pond.STATUS_DRAWN:
            status = Pond.STATUS_FILLING

        pond = Pond(
            plant_id=plant_id,
            code=code,
            status=status,
            capacity_m3=capacity,
            notes=notes,
        )
        db.session.add(pond)
        try:
            # 并发兜底：两人几乎同时提交同厂同号时，唯一约束
            # uq_pond_code_per_plant 只放行一笔，另一笔在此失败回滚。
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            plants = Plant.query.order_by(Plant.name).all()
            flash(f"厂区 {plant_name} 已存在同编号池 {code}，不能重复创建", "error")
            return render_template(
                "ponds/form.html",
                pond=None,
                plants=plants,
                status_labels=STATUS_LABELS,
            )

        if initial_status == Pond.STATUS_DRAWN:
            flash("新建池不能直接设为已出灰，已改为注水中", "error")
        flash("熟化池已创建", "ok")
        return redirect(url_for("board.floor_plan", plant_id=plant_id))
    return render_template(
        "ponds/form.html",
        pond=None,
        plants=plants,
        status_labels=STATUS_LABELS,
    )


@bp.route("/<int:pond_id>/edit", methods=["GET", "POST"])
@login_required
def edit_pond(pond_id: int):
    pond = Pond.query.get_or_404(pond_id)
    plants = Plant.query.order_by(Plant.name).all()
    if request.method == "POST":
        plant_id = int(request.form["plant_id"])
        code = (request.form.get("code") or "").strip()
        status = request.form.get("status") or pond.status
        capacity = float(request.form.get("capacity_m3") or 0)
        notes = (request.form.get("notes") or "").strip()
        dup = Pond.query.filter(
            Pond.plant_id == plant_id,
            Pond.code == code,
            Pond.id != pond.id,
        ).first()
        if dup:
            flash("同一厂区内池编号必须唯一", "error")
        else:
            try:
                assert_can_set_pond_status(pond, status)
                pond.plant_id = plant_id
                pond.code = code
                pond.status = status
                pond.capacity_m3 = capacity
                pond.notes = notes
                db.session.commit()
                flash("熟化池已更新", "ok")
                return redirect(url_for("board.floor_plan", plant_id=plant_id, pond=pond.id))
            except RuleError as exc:
                db.session.rollback()
                flash(str(exc), "error")
            except IntegrityError:
                # 并发下另一事务抢先占用了同厂同号。
                db.session.rollback()
                flash("同一厂区内池编号必须唯一", "error")
    return render_template(
        "ponds/form.html",
        pond=pond,
        plants=plants,
        status_labels=STATUS_LABELS,
    )
