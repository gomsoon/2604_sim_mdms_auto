from __future__ import annotations

from flask import Blueprint, render_template
from sqlalchemy import func, select

from app.db import get_session
from app.models import (
    CanonicalMeasurement,
    Device,
    HesEventRaw,
    HesReadRaw,
    IngestErrorLog,
    MeasuringComponent,
    ServicePoint,
)


bp = Blueprint("web", __name__)


@bp.get("/")
def dashboard():
    session = get_session()
    stats = {
        "service_points": session.scalar(select(func.count()).select_from(ServicePoint)) or 0,
        "devices": session.scalar(select(func.count()).select_from(Device)) or 0,
        "components": session.scalar(select(func.count()).select_from(MeasuringComponent)) or 0,
        "raw_reads": session.scalar(select(func.count()).select_from(HesReadRaw)) or 0,
        "raw_events": session.scalar(select(func.count()).select_from(HesEventRaw)) or 0,
        "canonical": session.scalar(select(func.count()).select_from(CanonicalMeasurement)) or 0,
        "exceptions": session.scalar(select(func.count()).select_from(IngestErrorLog)) or 0,
    }
    recent_reads = session.scalars(select(HesReadRaw).order_by(HesReadRaw.id.desc()).limit(10)).all()
    recent_exceptions = session.scalars(
        select(IngestErrorLog).order_by(IngestErrorLog.id.desc()).limit(10)
    ).all()
    return render_template(
        "dashboard.html",
        stats=stats,
        recent_reads=recent_reads,
        recent_exceptions=recent_exceptions,
    )


@bp.get("/raw-reads")
def raw_reads():
    session = get_session()
    rows = session.scalars(select(HesReadRaw).order_by(HesReadRaw.id.desc()).limit(100)).all()
    return render_template("raw_reads.html", rows=rows)


@bp.get("/raw-events")
def raw_events():
    session = get_session()
    rows = session.scalars(select(HesEventRaw).order_by(HesEventRaw.id.desc()).limit(100)).all()
    return render_template("raw_events.html", rows=rows)


@bp.get("/exceptions")
def exceptions():
    session = get_session()
    rows = session.scalars(
        select(IngestErrorLog).order_by(IngestErrorLog.id.desc()).limit(100)
    ).all()
    return render_template("exceptions.html", rows=rows)


@bp.get("/master-data")
def master_data():
    session = get_session()
    components = session.scalars(
        select(MeasuringComponent).order_by(MeasuringComponent.id.desc()).limit(100)
    ).all()
    return render_template("master_data.html", rows=components)
