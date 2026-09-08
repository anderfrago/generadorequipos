"""Scoring and feedback ported from the supplied Apps Script services."""
import json
from pathlib import Path
from .grouping_engine import PROFILES

QUESTIONNAIRE = json.loads(Path(__file__).with_name("questionnaire.json").read_text(encoding="utf-8"))
ITEMS = QUESTIONNAIRE["items"]
FUNCTION_CODES = list(dict.fromkeys(row[3] for row in ITEMS if row[0] == "B"))
SCALE = ["Nada como yo", "Poco como yo", "Bastante como yo", "Muy como yo"]


def pattern(scores):
    ordered = sorted(PROFILES, key=lambda k: -scores[k])
    maximum, second = scores[ordered[0]], scores[ordered[1]]
    gap = maximum - second
    involved = [k for k in PROFILES if scores[k] == maximum]
    kind, secondary = "CLEAR", ""
    if all(v == 0 for v in scores.values()):
        kind, involved = "NONE", []
    elif len(involved) == 4:
        kind = "BALANCED_4"
    elif len(involved) == 3:
        kind = "BALANCED_3"
    elif len(involved) == 2:
        kind = "COMBINED_2"
    elif gap == 1:
        involved = [k for k in PROFILES if maximum - scores[k] <= 1]
        kind = {2: "COMBINED_2", 3: "NEAR_3", 4: "NEAR_4"}[len(involved)]
    else:
        secondary = ordered[1]
    return dict(kind=kind, involved=involved, secondary=secondary, topGap=gap)


def profile_text(p):
    meta = QUESTIONNAIRE["profiles"]
    codes = p["involved"]
    labels = [meta[k]["label"] for k in codes]
    contributions = [meta[k]["contribution"] for k in codes]
    joined = ", ".join(labels[:-1]) + " y " + labels[-1] if len(labels) > 1 else (labels[0] if labels else "")
    if p["kind"] == "NONE":
        return ("Sin tendencia diferenciada en esta actividad.", "Tus respuestas no muestran una tendencia diferenciada hacia una de las cuatro funciones. Las formas de contribuir pueden aparecer de manera distinta según la tarea y el momento.")
    if p["kind"] == "BALANCED_4":
        return ("En esta actividad no aparece una tendencia claramente diferenciada: has mostrado una intensidad muy similar en las cuatro formas de contribuir al equipo.", "Tus respuestas reflejan recursos para impulsar, organizar, explorar e integrar. La aportación que aparezca con más fuerza puede variar según la tarea y el momento.")
    if len(codes) >= 3:
        return ("En esta actividad has mostrado un patrón especialmente equilibrado entre " + joined + ".", "Este patrón puede combinar " + "; ".join(contributions) + ". La función que tome más protagonismo puede depender de la situación.")
    if p["kind"] == "COMBINED_2":
        return ("En esta actividad has mostrado una combinación especialmente próxima de " + joined + ".", "Esta combinación puede aportar " + contributions[0] + " junto con " + contributions[1] + ".")
    secondary = meta.get(p["secondary"])
    return ("En esta actividad has mostrado mayor tendencia a " + labels[0] + ".", "Puedes aportar especialmente " + contributions[0] + "." + (" También aparece como siguiente tendencia " + secondary["label"] + ", relacionada con " + secondary["contribution"] + "." if secondary else ""))


def next_step(p, values, details):
    texts = QUESTIONNAIRE["personalization"]
    def low(k):
        return k in details and not details[k]["mixed"] and values[k] <= .40
    rules = [
        ("IMP", "ORGP", "Parece que te resulta relativamente fácil hacer que las cosas se pongan en marcha. "),
        ("IMP", "COMM", "Tu facilidad para iniciar puede ganar eficacia si compruebas que otras personas han podido aportar antes de cerrar una decisión. "),
        ("ORG", "ADAPT", "Tu capacidad para ordenar el trabajo puede complementarse con mayor flexibilidad cuando cambia un plan. "),
        ("ORG", "INIT", "La preparación resulta más útil cuando se transforma en primeros pasos concretos. "),
        ("EXP", "INIT", "Tus alternativas pueden ganar valor si se convierten en decisiones y primeros pasos concretos. "),
        ("EXP", "ORGP", "Tus ideas pueden ganar viabilidad si priorizas y seleccionas cuáles desarrollar. "),
        ("INT", "CONF", "Cuidar el funcionamiento del equipo también puede requerir abordar desacuerdos necesarios. "),
    ]
    for code, k, prefix in rules:
        if code in p["involved"] and low(k):
            return prefix + texts[k]["development"]
    for k in ("AUT", "RESP", "ORGP", "COMM", "CONF", "ADAPT", "INIT"):
        if low(k):
            return texts[k]["development"]
    return "Tus respuestas muestran recursos bastante equilibrados o evidencias mixtas. Un buen siguiente paso puede ser aprender a elegir qué forma de contribuir resulta más útil en cada situación: habrá momentos para tomar la iniciativa y otros para organizar, explorar alternativas o apoyar el funcionamiento común."


def calculate(answers, conditions=None, other=""):
    if set(answers) != {str(row[1]) for row in ITEMS} or any(type(v) is not int or v not in range(4) for v in answers.values()):
        raise ValueError("Faltan respuestas o contienen valores no válidos.")
    profiles = {k: 0 for k in PROFILES}
    functional = {k: 0 for k in FUNCTION_CODES}
    details = {}
    for block, number, text, dimension, reverse in ITEMS:
        raw = answers[str(number)]
        corrected = 3 - raw if reverse else raw
        if block == "A":
            profiles[dimension] += raw
        else:
            functional[dimension] += corrected
            d = details.setdefault(dimension, dict(QUESTIONNAIRE["functional"][dimension], items=[]))
            d["items"].append(dict(number=number, text=text, rawValue=raw, correctedValue=corrected, isReverse=reverse, response=SCALE[raw]))
    for d in details.values():
        vals = [i["correctedValue"] for i in d["items"]]
        d["mixed"] = len(vals) == 2 and abs(vals[0] - vals[1]) >= 2
    functional = {k: v / 6 for k, v in functional.items()}
    p = pattern(profiles)
    heading, explanation = profile_text(p)
    candidates = sorted((k for k in FUNCTION_CODES if k != "COOP" and not details[k]["mixed"] and functional[k] >= 2 / 3), key=lambda k: -functional[k])
    strengths = [QUESTIONNAIRE["personalization"][k]["strength"] for k in candidates[:2]] or ["Tus respuestas muestran recursos que pueden aparecer de forma diferente según la tarea. Sigue observando qué aportaciones resultan más útiles en cada situación."]
    labels = dict(QUESTIONNAIRE["conditions"])
    condition_text = ["Otra: " + other if k == "OTHER" and other else labels[k] for k in (conditions or [])]
    feedback = dict(heading=heading, explanation=explanation, pattern=p["kind"], involvedProfiles=p["involved"],
                    scores={k: round(v / 12 * 100) for k, v in profiles.items()}, strengths=strengths,
                    nextStep=next_step(p, functional, details), conditions=condition_text,
                    reminder="Este resultado orienta; no te encierra en un perfil ni decide automáticamente tu equipo.")
    return dict(profiles={k: v / 12 for k, v in profiles.items()}, raw=profiles, functional=functional,
                details=details, feedback=feedback, scoringVersion="V3R-1.0", questionnaireVersion=QUESTIONNAIRE["version"])
