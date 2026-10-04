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
    plant = db.session.get(Plant, plant_id)
    if plant is None:
        flash("厂区不存在或已删除", "error")
        return redirect(url_for("plants.list_plants"))
    plant_name = plant.name
    try:
        # 真删除：厂区、其下全部熟化池、池上全部熟化批次
        # 由外键 ON DELETE CASCADE 与 ORM cascade 在同一事务内完成；
        # 任一步失败整笔回滚，不允许留下只删厂名的孤儿池/批次。
        db.session.delete(plant)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash(f"厂区 {plant_name} 删除失败，已全部回滚", "error")
    else:
        flash(f"厂区 {plant_name} 及其池、批次已删除", "ok")
    return redirect(url_for("plants.list_plants"))
