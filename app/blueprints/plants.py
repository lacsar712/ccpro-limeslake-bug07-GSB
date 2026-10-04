from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required

from app.extensions import db
from app.models import Plant

bp = Blueprint("plants", __name__, url_prefix="/plants")


@bp.route("/")
@login_required
def list_plants():
    plants = Plant.query.order_by(Plant.name).all()
    return render_template("plants/list.html", plants=plants)


@bp.route("/<int:plant_id>/delete", methods=["POST"])
@login_required
def delete_plant(plant_id: int):
    plant = Plant.query.get_or_404(plant_id)
    plant_name = plant.name
    try:
        # 真删除：由 ORM 级联一并删除该厂区的熟化池与批次
        # （Plant.ponds / Pond.batches 均为 cascade="all, delete-orphan"），
        # 厂区、池、批次在同一事务内提交，任一失败整体回滚，不留孤儿数据。
        db.session.delete(plant)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash(f"厂区 {plant_name} 删除失败，已整体回滚", "error")
        return redirect(url_for("plants.list_plants"))
    flash(f"厂区 {plant_name} 已删除", "ok")
    return redirect(url_for("plants.list_plants"))
