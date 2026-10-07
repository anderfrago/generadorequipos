"""Additive migration and explicit deletion, including embedded proposal snapshots."""
from datetime import datetime, timezone, timedelta
import click
from flask import render_template_string
from .db import get_db


def migrate_privacy(db):
    with db:
        for table, name, declaration in (
            ("users", "auth_version", "INTEGER NOT NULL DEFAULT 1"),
            ("users", "google_subject", "TEXT"),
            ("enrollments", "token_expires_at", "TEXT"),
            ("classes", "privacy_updated_at", "TEXT"),
            ("proposals", "reviewed_by", "TEXT REFERENCES users(id)"),
            ("proposals", "reviewed_at", "TEXT"),
        ):
            if name not in {row[1] for row in db.execute(f"PRAGMA table_info({table})")}:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
        db.execute("UPDATE classes SET privacy_updated_at=? WHERE privacy_updated_at IS NULL", (datetime.now(timezone.utc).isoformat(),))
        # Existing links without expiration must be renewed; validated reports need a new review.
        db.execute("UPDATE enrollments SET token_hash=NULL WHERE token_expires_at IS NULL")
        db.execute("UPDATE proposals SET status='DRAFT' WHERE reviewed_at IS NULL AND status='VALIDATED'")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_google_subject ON users(google_subject)")
        db.execute("CREATE TABLE IF NOT EXISTS link_failures (key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires_at INTEGER NOT NULL)")
        db.execute("INSERT OR IGNORE INTO schema_version VALUES(2)")
    # Activity triggers also cover API writes that do not create an audit entry.
    for table, expression in (
        ("enrollments", "{ref}.class_id"), ("relations", "{ref}.class_id"),
        ("proposals", "{ref}.class_id"), ("class_teachers", "{ref}.class_id"),
        ("submissions", "(SELECT class_id FROM enrollments WHERE id={ref}.enrollment_id)"),
        ("observations", "(SELECT class_id FROM enrollments WHERE id={ref}.enrollment_id)"),
        ("invitation_deliveries", "(SELECT class_id FROM enrollments WHERE id={ref}.enrollment_id)"),
        ("manual_changes", "(SELECT class_id FROM proposals WHERE id={ref}.proposal_id)"),
    ):
        for action in ("INSERT", "UPDATE", "DELETE"):
            ref = "OLD" if action == "DELETE" else "NEW"
            db.execute(f"CREATE TRIGGER IF NOT EXISTS privacy_{table}_{action} AFTER {action} ON {table} BEGIN UPDATE classes SET privacy_updated_at=strftime('%Y-%m-%dT%H:%M:%f+00:00','now') WHERE id={expression.format(ref=ref)}; END")
    db.execute("CREATE TRIGGER IF NOT EXISTS privacy_classes_update AFTER UPDATE OF name,academic_year,evaluation_period,active,code ON classes BEGIN UPDATE classes SET privacy_updated_at=strftime('%Y-%m-%dT%H:%M:%f+00:00','now') WHERE id=NEW.id; END")
    db.execute("CREATE TRIGGER IF NOT EXISTS privacy_classes_insert AFTER INSERT ON classes BEGIN UPDATE classes SET privacy_updated_at=strftime('%Y-%m-%dT%H:%M:%f+00:00','now') WHERE id=NEW.id; END")
    db.commit()


def delete_proposal(db, proposal_id):
    db.execute("DELETE FROM manual_changes WHERE proposal_id=?", (proposal_id,))
    db.execute("DELETE FROM audit_log WHERE entity_id=?", (proposal_id,))
    db.execute("DELETE FROM proposals WHERE id=?", (proposal_id,))


def delete_enrollment(db, enrollment_id):
    db.execute("DELETE FROM invitation_deliveries WHERE enrollment_id=?", (enrollment_id,))
    db.execute("DELETE FROM observations WHERE enrollment_id=?", (enrollment_id,))
    db.execute("DELETE FROM submissions WHERE enrollment_id=?", (enrollment_id,))
    db.execute("DELETE FROM audit_log WHERE entity_id=?", (enrollment_id,))
    db.execute("DELETE FROM enrollments WHERE id=?", (enrollment_id,))


def erase_class(db, class_id):
    students = [r[0] for r in db.execute("SELECT student_id FROM enrollments WHERE class_id=?", (class_id,))]
    for row in db.execute("SELECT id FROM proposals WHERE class_id=?", (class_id,)).fetchall():
        delete_proposal(db, row[0])
    for row in db.execute("SELECT id FROM enrollments WHERE class_id=?", (class_id,)).fetchall():
        delete_enrollment(db, row[0])
    db.execute("DELETE FROM audit_log WHERE entity_id IN (SELECT id FROM relations WHERE class_id=?)", (class_id,))
    db.execute("DELETE FROM relations WHERE class_id=?", (class_id,))
    db.execute("DELETE FROM class_teachers WHERE class_id=?", (class_id,))
    db.execute("DELETE FROM audit_log WHERE entity_id=?", (class_id,))
    db.execute("DELETE FROM classes WHERE id=?", (class_id,))
    for student_id in students:
        if not db.execute("SELECT 1 FROM enrollments WHERE student_id=?", (student_id,)).fetchone():
            db.execute("DELETE FROM audit_log WHERE entity_id=?", (student_id,))
            db.execute("DELETE FROM students WHERE id=?", (student_id,))


def register_privacy(app):
    @app.cli.command("purge-link-failures")
    def purge_link_failures():
        import time
        with get_db():
            count=get_db().execute("DELETE FROM link_failures WHERE expires_at<=?",(int(time.time()),)).rowcount
        click.echo(f"Contadores caducados eliminados: {count}")

    @app.cli.command("purge-audit")
    @click.option("--execute", is_flag=True)
    def purge_audit(execute):
        """Preview/delete expired audit entries under their own approved policy."""
        try:
            days = int(app.config["AUDIT_RETENTION_DAYS"])
            if days <= 0: raise ValueError
        except (TypeError, ValueError):
            raise click.ClickException("Define AUDIT_RETENTION_DAYS como entero positivo aprobado por el centro")
        cutoff = (datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
        db=get_db()
        with db:
            db.execute("BEGIN IMMEDIATE")
            count=db.execute("SELECT COUNT(*) FROM audit_log WHERE created_at<?",(cutoff,)).fetchone()[0]
            if execute: db.execute("DELETE FROM audit_log WHERE created_at<?",(cutoff,))
            click.echo(f"{'Borrados' if execute else 'Vista previa sin borrado'}: {count} registros de auditoría")

    @app.cli.command("purge-expired")
    @click.option("--class-id", multiple=True)
    @click.option("--execute", is_flag=True)
    def purge_expired(class_id, execute):
        """Preview expired inactive classes; deletion requires explicit identifiers."""
        try:
            days = int(app.config["RETENTION_DAYS"])
            if days <= 0: raise ValueError
        except (ValueError, TypeError):
            raise click.ClickException("Define RETENTION_DAYS como entero positivo aprobado por el centro")
        db = get_db()
        with db:
            db.execute("BEGIN IMMEDIATE")
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            eligible = {r["id"] for r in db.execute("SELECT * FROM classes WHERE active=0")
                        if r["privacy_updated_at"] and datetime.fromisoformat(r["privacy_updated_at"]) < cutoff}
            selected = set(class_id)
            if selected - eligible: raise click.ClickException("Hay clases activas, recientes o desconocidas. No se ha borrado nada")
            if execute and not selected: raise click.ClickException("Selecciona cada --class-id revisado")
            targets = sorted(selected or eligible)
            for identifier in targets:
                count = db.execute("SELECT COUNT(*) FROM enrollments WHERE class_id=?", (identifier,)).fetchone()[0]
                click.echo(f"Clase {identifier}: {count} matrículas")
                if execute: erase_class(db, identifier)
            click.echo(f"{'Borradas' if execute else 'Vista previa sin borrado'}: {len(targets)} clases")

    @app.cli.command("erase-student")
    @click.option("--student-id", required=True)
    @click.option("--execute", is_flag=True)
    def erase_student(student_id, execute):
        """Explicit data-subject erasure; also remove proposals containing their snapshots."""
        db = get_db()
        with db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM students WHERE id=?", (student_id,)).fetchone():
                raise click.ClickException("Alumno no encontrado")
            proposals = db.execute("SELECT DISTINCT p.id FROM proposals p LEFT JOIN manual_changes m ON m.proposal_id=p.id WHERE instr(p.source_model,?)>0 OR instr(p.data,?)>0 OR instr(m.before_data,?)>0", (student_id,student_id,student_id)).fetchall()
            enrollments = db.execute("SELECT id FROM enrollments WHERE student_id=?", (student_id,)).fetchall()
            click.echo(f"Alumno {student_id}: {len(enrollments)} matrículas y {len(proposals)} propuestas completas afectadas")
            if not execute:
                click.echo("Vista previa: no se ha borrado nada")
                return
            for row in proposals: delete_proposal(db, row[0])
            for row in enrollments: delete_enrollment(db, row[0])
            db.execute("DELETE FROM audit_log WHERE entity_id IN (SELECT id FROM relations WHERE student_a=? OR student_b=?)", (student_id,student_id))
            db.execute("DELETE FROM relations WHERE student_a=? OR student_b=?", (student_id,student_id))
            db.execute("DELETE FROM audit_log WHERE entity_id=?", (student_id,))
            db.execute("DELETE FROM students WHERE id=?", (student_id,))
            click.echo("Datos del alumno y propuestas afectadas eliminados")

    @app.get("/privacidad")
    def privacy():
        fields = [(label, app.config[key]) for label,key in (
            ("Responsable", "PRIVACY_CONTROLLER"), ("Contacto y derechos", "PRIVACY_CONTACT"),
            ("Base jurídica", "PRIVACY_LEGAL_BASIS"), ("Conservación", "PRIVACY_RETENTION"),
            ("Proveedores y transferencias", "PRIVACY_PROVIDERS"))]
        return render_template_string('''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Privacidad · Equipos equilibrados</title>
        <main style="max-width:55rem;margin:2rem auto;padding:1rem;font:1.1rem/1.6 system-ui"><h1>Privacidad · Equipos equilibrados</h1>
        {% if incomplete %}<p><strong>Información pendiente de validar por el centro antes de usar con alumnado.</strong></p>{% endif %}
        <p>Se tratan identidad, matrícula, respuestas, preferencias de trabajo, observaciones docentes, relaciones entre estudiantes y propuestas de equipos para orientar el trabajo en el aula.</p>
        <p>El profesorado autorizado de cada clase y la administración pueden consultar estos datos. El enlace individual permite ver y modificar el cuestionario propio: no debe compartirse. Las exportaciones deben conservarse en destinos institucionales autorizados.</p>
        <p>Los perfiles se calculan mediante reglas y no son diagnósticos ni calificaciones. Las propuestas necesitan revisión humana antes de validarse. No incluyas diagnósticos, información clínica ni detalles privados de otras personas en los textos libres.</p>
        {% for label,value in fields %}<h2>{{label}}</h2><p>{{value or 'Pendiente de definición por el centro.'}}</p>{% endfor %}
        <p>Puedes solicitar acceso, rectificación, supresión y los demás derechos que correspondan mediante el contacto indicado y reclamar ante la AEPD.</p>
        <p>Se utilizan cookies necesarias de sesión y protección de solicitudes. Google verifica el acceso docente; el proveedor SMTP interviene cuando el centro envía invitaciones.</p></main></html>''', fields=fields, incomplete=any(not value for _,value in fields))
