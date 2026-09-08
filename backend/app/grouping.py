import copy
import json
import time
from flask import Blueprint, abort, g, jsonify
from .auth import teacher, class_access
from .classes import now, uid, audit, payload
from .db import get_db
from .grouping_engine import evaluate, generate, prepare_model, size_options
from .scoring import FUNCTION_CODES

bp = Blueprint("grouping", __name__, url_prefix="/api")


def current_relations(class_id):
    return [dict(a=r["student_a"], b=r["student_b"], type=r["type"]) for r in get_db().execute("SELECT * FROM relations WHERE class_id=?", (class_id,))]


def build_model(class_id):
    students = []
    for row in get_db().execute(
        "SELECT s.id,s.name,x.id submission_id,x.result,x.conditions FROM enrollments e JOIN students s ON s.id=e.student_id "
        "JOIN submissions x ON x.enrollment_id=e.id AND x.revision=(SELECT MAX(y.revision) FROM submissions y WHERE y.enrollment_id=e.id) "
        "WHERE e.class_id=? AND e.active=1 AND x.status='SUBMITTED' AND x.result IS NOT NULL", (class_id,)
    ):
        result = json.loads(row["result"])
        students.append(dict(id=row["id"], name=row["name"], submission_id=row["submission_id"], profiles=result["profiles"],
                             functional=result["functional"], conditions=json.loads(row["conditions"])))
    if len(students) < 3:
        abort(400, "Se necesitan al menos tres cuestionarios completos para formar equipos.")
    return prepare_model(students, current_relations(class_id), FUNCTION_CODES)


def proposal_row(proposal_id):
    row = get_db().execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
    if not row:
        abort(404, "Propuesta no encontrada.")
    class_access(row["class_id"])
    return row


def public(row):
    return dict(json.loads(row["data"]), id=row["id"], class_id=row["class_id"], status=row["status"],
                kind=row["kind"], version=row["version"], created_at=row["created_at"])


def check_partition(model, teams):
    flat = [sid for team in teams for sid in team]
    if len(flat) != len(set(flat)) or set(flat) != set(model["by_id"]) or any(not 3 <= len(t) <= 5 for t in teams):
        abort(400, "Los equipos deben incluir a cada persona una sola vez y tener entre 3 y 5 integrantes.")


@bp.get("/classes/<class_id>/size-options")
@teacher
def sizes(class_id):
    class_access(class_id)
    return jsonify(size_options(len(build_model(class_id)["students"])))


@bp.get("/classes/<class_id>/proposals")
@teacher
def history(class_id):
    class_access(class_id)
    return jsonify([dict(id=r["id"], kind=r["kind"], status=r["status"], created_at=r["created_at"],
                         balanceIndex=json.loads(r["data"])["metrics"]["balanceIndex"])
                    for r in get_db().execute("SELECT * FROM proposals WHERE class_id=? ORDER BY created_at DESC", (class_id,))])


@bp.get("/proposals/<proposal_id>")
@teacher
def detail(proposal_id):
    return jsonify(public(proposal_row(proposal_id)))


@bp.post("/classes/<class_id>/proposals")
@teacher
def generate_proposal(class_id):
    class_access(class_id)
    data = payload()
    model = build_model(class_id)
    sizes = data.get("sizes")
    if not isinstance(sizes, list):
        abort(400, "Selecciona una distribución.")
    reference = None
    reference_id = data.get("reference_id")
    if reference_id:
        row = proposal_row(reference_id)
        if row["class_id"] != class_id:
            abort(400, "La propuesta de referencia debe pertenecer a esta clase.")
        reference = json.loads(row["data"])
        if set(x for team in reference["teams"] for x in team) != set(model["by_id"]):
            abort(409, "El alumnado elegible ha cambiado. Genera una propuesta nueva.")
    result = None
    try:
        for attempt in range(4 if reference else 1):
            candidate = generate(model, sizes, reference=reference["teams"] if reference else None)
            if not reference or (candidate["metrics"]["weakestTeamIndex"] >= reference["metrics"]["weakestTeamIndex"] - 5
                                 and candidate["metrics"]["differenceFromReference"] >= .28):
                result = candidate
                break
    except ValueError as error:
        abort(400, str(error))
    if result is None:
        abort(422, "No se encontró una alternativa suficientemente diferente con equilibrio semejante. Prueba otra distribución.")
    result.update(locked=[False] * len(sizes), reference_id=reference_id,
                  names={s["id"]: s["name"] for s in model["students"]})
    proposal_id = uid()
    db = get_db()
    with db:
        # Detect source changes during the potentially long search before persisting.
        db.execute("BEGIN IMMEDIATE")
        fresh = build_model(class_id)
        if fresh != model:
            abort(409, "Las respuestas o relaciones han cambiado durante la búsqueda. Vuelve a generar.")
        db.execute("INSERT INTO proposals(id,class_id,kind,data,source_model,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
                   (proposal_id, class_id, "ALTERNATIVE" if reference else "RECOMMENDED", json.dumps(result), json.dumps(model), g.user["id"], now()))
        audit("GENERATE_TEAMS", proposal_id)
    return jsonify(public(proposal_row(proposal_id)))


@bp.post("/proposals/<proposal_id>/change")
@teacher
def change(proposal_id):
    request_data = payload()
    # Serialize competing manual edits. Computation is bounded; deployment targets small classes.
    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        row = proposal_row(proposal_id)
        if request_data.get("version") != row["version"]:
            abort(409, "Otra persona ha modificado esta propuesta. Vuelve a abrirla desde el historial.")
        action = request_data.get("action")
        data = json.loads(row["data"])
        before = copy.deepcopy(data)
        model = json.loads(row["source_model"])
        model["relations"] = current_relations(row["class_id"])
        status = row["status"]
        if status == "VALIDATED" and action != "reopen":
            abort(409, "Reabre la propuesta antes de modificarla.")
        teams, locked = data["teams"], data["locked"]
        if action == "reopen":
            status = "DRAFT"
        elif action == "validate":
            status = "VALIDATED"
        elif action == "lock":
            i = request_data.get("index")
            if type(i) is not int or not 0 <= i < len(teams) or type(request_data.get("locked")) is not bool:
                abort(400, "Equipo no válido.")
            locked[i] = request_data["locked"]
        elif action in ("swap", "move"):
            a_id = request_data.get("a") if action == "swap" else request_data.get("student")
            a = next((i for i, t in enumerate(teams) if a_id in t), -1)
            b_id = request_data.get("b")
            b = next((i for i, t in enumerate(teams) if b_id in t), -1) if action == "swap" else request_data.get("to")
            if a < 0 or type(b) is not int or not 0 <= b < len(teams) or a == b:
                abort(400, "Selecciona personas de equipos diferentes o un equipo de destino válido.")
            if locked[a] or locked[b]:
                abort(409, "Desbloquea los equipos afectados antes de modificarlos.")
            if action == "swap":
                ia, ib = teams[a].index(a_id), teams[b].index(b_id)
                teams[a][ia], teams[b][ib] = teams[b][ib], teams[a][ia]
            else:
                teams[a].remove(a_id)
                teams[b].append(a_id)
        elif action == "regenerate":
            indexes = [i for i in range(len(teams)) if not locked[i]]
            if len(indexes) < 2:
                abort(400, "Deben quedar al menos dos equipos sin bloquear.")
            ids = {sid for i in indexes for sid in teams[i]}
            sub = dict(model, students=[s for s in model["students"] if s["id"] in ids], by_id={sid: model["by_id"][sid] for sid in ids})
            try:
                result = generate(sub, [len(teams[i]) for i in indexes])
            except ValueError as error:
                abort(400, str(error))
            for i, team in zip(indexes, result["teams"]):
                teams[i] = team
        elif action == "undo":
            last = db.execute("SELECT * FROM manual_changes WHERE proposal_id=? AND undone=0 ORDER BY id DESC LIMIT 1", (proposal_id,)).fetchone()
            if not last:
                abort(400, "No hay cambios que deshacer.")
            data = json.loads(last["before_data"])
            teams = data["teams"]
            db.execute("UPDATE manual_changes SET undone=1 WHERE id=?", (last["id"],))
        else:
            abort(400, "Acción no reconocida.")
        check_partition(model, teams)
        metrics = evaluate(model, teams)
        if not metrics["hardConstraintsOk"]:
            abort(400, "La propuesta incumple una restricción NO JUNTAR vigente.")
        data["metrics"] = metrics
        if action in ("lock", "swap", "move", "regenerate"):
            db.execute("INSERT INTO manual_changes(proposal_id,before_data,created_at) VALUES(?,?,?)", (proposal_id, json.dumps(before), now()))
        db.execute("UPDATE proposals SET data=?,status=?,version=version+1 WHERE id=?", (json.dumps(data), status, proposal_id))
        audit("PROPOSAL_" + action.upper(), proposal_id)
    return jsonify(public(proposal_row(proposal_id)))
