"""On-demand PDF and CSV downloads. Nothing is stored in Google Drive."""
import csv
import io
import json
from xml.sax.saxutils import escape
from flask import Blueprint, abort, jsonify, make_response, send_file
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak, KeepTogether
from .auth import teacher, class_access
from .classes import class_detail, enrollment
from .students import latest
from .grouping import proposal_row, public
from .scoring import QUESTIONNAIRE, FUNCTION_CODES
from .db import get_db

bp = Blueprint("reports", __name__, url_prefix="/api")
GREEN = colors.HexColor("#285b4c")
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="ReportTitle", fontName="Helvetica-Bold", fontSize=22, leading=27, textColor=GREEN, spaceAfter=12))
styles.add(ParagraphStyle(name="ReportHeading", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=GREEN, spaceBefore=10, spaceAfter=5, keepWithNext=True))
styles.add(ParagraphStyle(name="ReportBody", fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=6))


def p(text, style="ReportBody"):
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[style])


def pdf_bytes(story, title):
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=22*mm,
                            title=title, author="Equipos equilibrados")
    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dce3dd"))
        canvas.line(20*mm, 17*mm, 190*mm, 17*mm)
        canvas.setFillColor(colors.HexColor("#66746f"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(20*mm, 12*mm, "Equipos equilibrados · Orientación para el trabajo en el aula")
        canvas.drawRightString(190*mm, 12*mm, str(document.page))
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def table(rows, widths):
    result = Table([[p(cell) for cell in row] for row in rows], colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#eaf0e8")),
                               ("VALIGN", (0,0), (-1,-1), "TOP"), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
                               ("TOPPADDING", (0,0), (-1,-1), 6), ("LINEBELOW", (0,0), (-1,-1), .4, colors.HexColor("#dce3dd"))]))
    return result


def individual_pdf(name, cls_name, result, observation, open_response):
    fb = result["feedback"]
    story = [p("Ficha de observación docente", "ReportTitle"), p(name + " · " + cls_name),
             p("A · Autoobservación del alumnado", "ReportHeading"), p(fb["heading"]), p(fb["explanation"]),
             p("Fortalezas y próximo paso", "ReportHeading")]
    story += [p(text) for text in fb["strengths"]] + [p(fb["nextStep"])]
    rows = [["Indicador funcional", "Valor", "Lectura"]]
    for k, value in result["functional"].items():
        rows.append([QUESTIONNAIRE["functional"][k]["label"], f"{value*100:.0f} %", "Evidencias mixtas" if result["details"][k]["mixed"] else "Respuestas coherentes"])
    story += [p("Indicadores funcionales", "ReportHeading"), p("Son respuestas de autoobservación, no notas ni diagnósticos."), table(rows, [85*mm,25*mm,60*mm]),
              p("Condiciones que ayudan a trabajar", "ReportHeading"), p(" · ".join(fb["conditions"]) or "Sin condiciones seleccionadas.")]
    if open_response:
        story += [p("Respuesta abierta literal", "ReportHeading"), p(open_response)]
    if observation:
        observation_block = [p("B · Observación docente registrada", "ReportHeading"), p("Información registrada por el profesorado, separada de la autoobservación.")]
        for key, label in [("free_text", "Notas"), ("autonomy_observed", "Autonomía"), ("responsibility_observed", "Responsabilidad"), ("organization_observed", "Organización"), ("other_functional_needs", "Otras necesidades")]:
            if observation.get(key):
                observation_block.append(p(label + ": " + str(observation[key])))
        story.append(KeepTogether(observation_block))
    story += [p("Cómo acompañar", "ReportHeading"), p("Contrastar estas hipótesis en distintas tareas. Acordar responsabilidades claras, practicar un próximo paso concreto y revisar el progreso con el alumno o alumna."), p(fb["reminder"])]
    return pdf_bytes(story, "Ficha docente - " + name)


def team_pdf(cls_name, data, scope):
    story = []
    for i, team in enumerate(data["teams"]):
        if i:
            story.append(PageBreak())
        tm = data["metrics"]["teamMetrics"][i]
        story += [p("Equipo " + str(i + 1), "ReportTitle"), p(cls_name + " · " + ("Informe docente" if scope == "teacher" else "Acuerdos de trabajo")),
                  p("Integrantes", "ReportHeading")]
        story += [p(data["names"].get(sid, sid)) for sid in team]
        if scope == "teacher":
            story += [p("Cómo leer esta propuesta", "ReportHeading"), p("Los índices permiten comparar combinaciones de equipos. No son notas, no miden la capacidad de las personas y no predicen si el equipo funcionará bien o mal."),
                      p(f"Índice de equilibrio: {tm['balanceIndex']} / 100"),
                      table([["Componente", "Cobertura / 100"]] + [[label, str(tm["components"][k])] for k, label in
                            [("profiles", "Perfiles"), ("functional", "Funcionamiento práctico"), ("complementarity", "Complementariedad"), ("conditions", "Condiciones de trabajo"), ("relations", "Relaciones docentes")]], [130*mm,40*mm]),
                      p("Aspectos para observar", "ReportHeading")]
            story += [p(w) for w in tm["warnings"]] or [p("No se han detectado alertas de equilibrio en esta combinación.")]
        story += [p("Acuerdos para empezar", "ReportHeading"),
                  p("1. Definid el objetivo común y divididlo en tareas concretas."),
                  p("2. Acordad quién se responsabiliza de cada tarea y cuándo debe estar terminada."),
                  p("3. Compartid avances y dificultades. Ofreced ayuda sin asumir automáticamente responsabilidades ajenas."),
                  p("4. Revisad los acuerdos si aparece un bloqueo o cambia el plan."),
                  p("Condiciones compartidas", "ReportHeading")]
        labels = dict(QUESTIONNAIRE["conditions"])
        story += [p(labels[c]) for c in tm.get("sharedConditions", [])] or [p("Conversad sobre qué condiciones os ayudan a trabajar y acordad cuáles podéis facilitar.")]
        story += [p("Revisión del equipo", "ReportHeading"), p("¿Qué nos está ayudando? ¿Qué debemos cambiar? ¿Cuál será nuestro siguiente acuerdo?"),
                  p("Este informe orienta el trabajo compartido. Las aportaciones de cada persona pueden variar según la tarea y el momento.")]
    return pdf_bytes(story, "Equipos - " + cls_name)


def download_pdf(content, filename):
    return send_file(io.BytesIO(content), mimetype="application/pdf", as_attachment=True, download_name=filename)


def csv_response(rows, filename):
    def safe(value):
        value = str(value if value is not None else "")
        return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerows([[safe(v) for v in row] for row in rows])
    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="' + filename + '"'
    return response


@bp.get("/classes/<class_id>/students/<student_id>/report")
@teacher
def student_report(class_id, student_id):
    cls = class_access(class_id)
    en = enrollment(class_id, student_id)
    sub = latest(en["id"])
    if not sub or not sub["result"] or sub["status"] != "SUBMITTED":
        abort(400, "El alumno no tiene resultados completos.")
    student = get_db().execute("SELECT name FROM students WHERE id=?", (student_id,)).fetchone()
    observation = get_db().execute("SELECT data FROM observations WHERE enrollment_id=?", (en["id"],)).fetchone()
    return download_pdf(individual_pdf(student["name"], cls["name"], json.loads(sub["result"]), json.loads(observation["data"]) if observation else {}, sub["open_response"]), "ficha-docente.pdf")


@bp.get("/proposals/<proposal_id>/report/<scope>")
@teacher
def proposal_report(proposal_id, scope):
    row = proposal_row(proposal_id)
    if row["status"] != "VALIDATED":
        abort(409, "Valida la propuesta antes de descargar informes.")
    if scope not in ("teacher", "student"):
        abort(404)
    cls = class_access(row["class_id"])
    return download_pdf(team_pdf(cls["name"], json.loads(row["data"]), scope), "equipos-" + scope + ".pdf")


@bp.get("/classes/<class_id>/export/<format>")
@teacher
def export_class(class_id, format):
    class_access(class_id)
    detail = class_detail.__wrapped__(class_id).get_json()
    if format == "json":
        response = jsonify(detail)
        response.headers["Content-Disposition"] = 'attachment; filename="resultados.json"'
        return response
    if format != "csv":
        abort(404)
    rows = [["Nombre", "Correo", "Estado"] + list(QUESTIONNAIRE["profiles"]) + [QUESTIONNAIRE["functional"][k]["label"] for k in FUNCTION_CODES] + ["Condiciones"]]
    for student in detail["students"]:
        result = student["result"] or {}
        rows.append([student["name"], student["email"], student["status"]] + [result.get("raw", {}).get(k, "") for k in QUESTIONNAIRE["profiles"]]
                    + [result.get("functional", {}).get(k, "") for k in FUNCTION_CODES] + [" | ".join(result.get("feedback", {}).get("conditions", []))])
    return csv_response(rows, "resultados.csv")


@bp.get("/proposals/<proposal_id>/export/csv")
@teacher
def export_teams(proposal_id):
    data = public(proposal_row(proposal_id))
    rows = [["Propuesta", "Estado", "Equipo", "Alumno/a", "Índice de equilibrio"]]
    for i, team in enumerate(data["teams"]):
        rows += [[proposal_id, data["status"], i + 1, data["names"].get(sid, sid), data["metrics"]["teamMetrics"][i]["balanceIndex"]] for sid in team]
    return csv_response(rows, "equipos.csv")
