from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required

from app.extensions import db
from app.models import Plant

bp = Blueprint("plants", __name__, url_prefix="/plants")

REMOVED_MARK = "[removed]"


@bp.route("/")
@login_required
def list_plants():
    plants = Plant.query.order_by(Plant.name).all()
    return render_template("plants/list.html", plants=plants, removed_mark=REMOVED_MARK)


@bp.route("/<int:plant_id>/delete", methods=["POST"])
@login_required
def delete_plant(plant_id: int):
    plant = Plant.query.get_or_404(plant_id)
    # 假删除：只打标，池与批次仍挂旧厂
    if REMOVED_MARK not in (plant.notes or ""):
        plant.notes = ((plant.notes or "").strip() + " " + REMOVED_MARK).strip()
    db.session.commit()
    flash(f"厂区 {plant.name} 已删除", "ok")
    return redirect(url_for("plants.list_plants"))
