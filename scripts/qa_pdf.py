"""Generate synthetic reports for visual verification; never uses real student data."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.scoring import calculate, ITEMS, FUNCTION_CODES
from app.grouping_engine import prepare_model, evaluate
from app.reports import individual_pdf, team_pdf

out = ROOT / "tmp" / "pdfs"
out.mkdir(parents=True, exist_ok=True)
answers = {str(row[1]): (row[1] % 4) for row in ITEMS}
result = calculate(answers, ["CALM", "STEPS", "OTHER"], "Disponer de tiempo para revisar el trabajo.")
(out / "individual.pdf").write_bytes(individual_pdf("María García López", "1.º Desarrollo de aplicaciones", result,
    {"free_text": "Se organiza con una lista de tareas y solicita ayuda cuando encuentra dificultades.", "autonomy_observed":"3"},
    "Me ayuda conocer con antelación las tareas y poder preguntar cuando tengo dudas."))
students = [dict(id=str(i),name=name,profiles=result["profiles"],functional=result["functional"],conditions=["CALM"]) for i,name in enumerate(["María García López","Álvaro Muñoz","Lucía Fernández","José Martín","Iñaki Pérez","Nerea Jiménez"])]
model = prepare_model(students, [], FUNCTION_CODES)
teams = [["0","1","2"],["3","4","5"]]
data = dict(teams=teams,names={s['id']:s['name'] for s in students},metrics=evaluate(model,teams))
for scope in ("teacher","student"):
    (out / (scope + ".pdf")).write_bytes(team_pdf("1.º Desarrollo de aplicaciones", data, scope))
print(out)
