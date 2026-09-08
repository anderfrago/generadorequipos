"""Python port of GroupingEngine.gs. Scores are comparison aids, not grades."""
import math
import random
import time
from collections import Counter
from statistics import mean

PROFILES = ("IMP", "ORG", "EXP", "INT")
CRITICAL = ("AUT", "RESP", "ORGP", "CONF", "ADAPT", "INIT")
WEIGHTS = dict(profiles=.30, functional=.35, complementarity=.15, conditions=.05, relations=.15)


def clamp(value, low=0, high=1):
    return max(low, min(high, value))


def second(values):
    values = sorted(values, reverse=True)
    return values[min(1, len(values) - 1)] if values else 0


def quantile(values, q):
    values = sorted(values)
    p = (len(values) - 1) * q
    i = math.floor(p)
    return values[i] + (p - i) * (values[min(i + 1, len(values) - 1)] - values[i])


def size_options(n):
    options = []
    for threes in range(n // 3 + 1):
        for fives in range(n // 5 + 1):
            remainder = n - 3 * threes - 5 * fives
            if remainder < 0 or remainder % 4:
                continue
            sizes = [3] * threes + [4] * (remainder // 4) + [5] * fives
            if not sizes:
                continue
            score = (threes + fives) * 10 + (max(sizes) - min(sizes)) * 4 + threes * 3 + fives
            options.append(dict(sizes=sizes, preferenceScore=score))
    return sorted(options, key=lambda x: x["preferenceScore"])[:3]


def prepare_model(students, relations, functional_codes, functional_weights=None):
    means = {k: mean(s["functional"][k] for s in students) for k in functional_codes}
    thresholds = {k: min(.5, quantile([s["functional"][k] for s in students], .35)) for k in CRITICAL}
    weak_share = {k: sum(s["functional"][k] <= thresholds[k] for s in students) / len(students) for k in CRITICAL}
    return dict(students=students, relations=relations, functional_codes=functional_codes,
                functional_weights=functional_weights or {k: 1 for k in functional_codes},
                means=means, thresholds=thresholds, weak_share=weak_share,
                by_id={s["id"]: s for s in students}, weights=WEIGHTS)


def evaluate_team(model, ids):
    members = [model["by_id"][sid] for sid in ids]
    n = len(members)
    pc = {}
    for k in PROFILES:
        values = [s["profiles"][k] for s in members]
        pc[k] = clamp(.5 * min(1, sum(values) / (n * .55)) + .3 * max(values) + .2 * second(values))
    ps = .65 * min(pc.values()) + .35 * mean(pc.values())
    fc = {}
    for k in model["functional_codes"]:
        values = [s["functional"][k] for s in members]
        class_mean = model["means"][k] or .5  # parity with the original JS fallback
        fc[k] = clamp(.55 * mean(values) + .25 * second(values) + .2 * (1 - min(1, abs(mean(values) - class_mean))))
    fw = model["functional_weights"]
    fs = sum(fc[k] * fw[k] for k in fc) / sum(fw.values())
    comp = []
    for a, b in (("EXP", "INIT"), ("IMP", "ORGP"), ("IMP", "COMM"), ("ADAPT", "INIT")):
        av = [s["profiles"][a] if a in PROFILES else s["functional"][a] for s in members]
        bv = [s["functional"][b] for s in members]
        comp.append(min(1, (mean(av) + mean(bv)) / 1.25) * min(1, (second(av) + second(bv)) / .8))
    counts = Counter(c for s in members for c in s["conditions"] if c not in ("NONE", "OTHER"))
    shared = [c for c, count in counts.items() if count >= 2]
    cs = clamp(.55 + len(shared) * .07)
    rs = 1
    for r in model["relations"]:
        both = r["a"] in ids and r["b"] in ids
        either = r["a"] in ids or r["b"] in ids
        if both and r["type"] == "MEJOR_SEPARADOS":
            rs -= .22
        elif either and not both and r["type"] == "CONVIENE_JUNTOS":
            rs -= .10
    components = dict(profiles=ps, functional=fs, complementarity=mean(comp), conditions=cs, relations=clamp(rs))
    warnings = []
    concentration = 0
    for k in CRITICAL:
        count = sum(s["functional"][k] <= model["thresholds"][k] for s in members)
        share = count / n
        if count >= 2 and share - model["weak_share"][k] >= .20:
            concentration += share * 16 / len(CRITICAL) * 2
            warnings.append(f"{k}: {count} de {n} miembros presentan valores bajos. Revisar el reparto de apoyos.")
    concentration = min(16, concentration)
    dominant = 0
    for student in members:
        count = 0
        for k in ("AUT", "RESP", "ORGP", "INIT", "COMM"):
            values = [s["functional"][k] for s in members]
            top = max(values)
            if student["functional"][k] == top and top - second(values) >= .28 and top >= .58:
                count += 1
        dominant = max(dominant, count)
    dependency = min(18, (dominant - 2) * 6) if dominant >= 3 else 0
    if dependency:
        warnings.append("Varias funciones clave dependen de una sola persona. Revisar responsabilidades.")
    severe = min(15, sum(v < .35 for v in pc.values()) * 3 + sum(v < .38 for v in fc.values()) * 1.5)
    if severe >= 6:
        warnings.append("Coinciden varias áreas con cobertura baja; contrastar la combinación en el aula.")
    base = 100 * sum(model["weights"][k] * v for k, v in components.items())
    return dict(balanceIndex=round(clamp(base - concentration - dependency - severe, 0, 100), 1),
                components={k: round(v * 100, 1) for k, v in components.items()},
                profileCoverage={k: round(v * 100, 1) for k, v in pc.items()},
                functionalCoverage={k: round(v * 100, 1) for k, v in fc.items()},
                penalties=dict(concentration=round(concentration, 2), dependency=dependency, severeImbalance=severe),
                warnings=warnings, sharedConditions=shared)


def distance(teams, reference):
    def pairs(partition):
        return {tuple(sorted((a, b))) for team in partition for i, a in enumerate(team) for b in team[i + 1:]}
    a, b = pairs(teams), pairs(reference)
    return len(a ^ b) / len(a | b) if a | b else 0


def evaluate(model, teams, reference=None):
    violations = [[r["a"], r["b"]] for r in model["relations"] if r["type"] == "NO_JUNTAR"
                  for team in teams if r["a"] in team and r["b"] in team]
    metrics = [evaluate_team(model, team) for team in teams]
    indexes = [m["balanceIndex"] for m in metrics]
    weak, best, average = min(indexes), max(indexes), mean(indexes)
    spread = best - weak
    penalties = sum(sum(m["penalties"].values()) for m in metrics)
    return dict(hardConstraintsOk=not violations, hardViolations=violations, teamMetrics=metrics,
                weakestTeamIndex=weak, bestTeamIndex=best, meanIndex=round(average, 1), spread=round(spread, 1),
                balanceIndex=round(.55 * weak + .25 * average + .2 * (100 - spread), 1),
                penaltyTotal=round(penalties, 2), differenceFromReference=distance(teams, reference) if reference else 1,
                warnings=[f"Equipo {i + 1}: {w}" for i, m in enumerate(metrics) for w in m["warnings"]])


def rank(m):
    return (m["hardConstraintsOk"], m["weakestTeamIndex"], -m["penaltyTotal"], -m["spread"], m["meanIndex"], m["differenceFromReference"])


def scalar(m):
    return (1e9 if m["hardConstraintsOk"] else 0) + m["weakestTeamIndex"] * 1e6 - m["penaltyTotal"] * 1e4 - m["spread"] * 1e3 + m["meanIndex"] * 100 + m["differenceFromReference"] * 20


def generate(model, sizes, seed=None, seconds=4.5, reference=None, iterations=2200, restarts=24):
    if not sizes or any(type(n) is not int or not 3 <= n <= 5 for n in sizes) or sum(sizes) != len(model["students"]):
        raise ValueError("La distribución debe incluir a todo el alumnado elegible en equipos de 3 a 5.")
    seed = seed if seed is not None else time.time_ns() % 2147483647
    rng = random.Random(seed)
    deadline = time.monotonic() + seconds
    best = None
    for _ in range(restarts):
        ids = list(model["by_id"])
        rng.shuffle(ids)
        teams, offset = [], 0
        for size in sizes:
            teams.append(ids[offset:offset + size])
            offset += size
        # Repair infeasible initial partitions, preserving all students and team sizes.
        current = evaluate(model, teams, reference)
        for _ in range(500):
            if current["hardConstraintsOk"] or len(teams) < 2 or time.monotonic() >= deadline:
                break
            a_id = current["hardViolations"][0][0]
            a = next(i for i, t in enumerate(teams) if a_id in t)
            b = rng.choice([i for i in range(len(teams)) if i != a])
            ia, ib = teams[a].index(a_id), rng.randrange(len(teams[b]))
            teams[a][ia], teams[b][ib] = teams[b][ib], teams[a][ia]
            current = evaluate(model, teams, reference)
        if current["hardConstraintsOk"] and (best is None or rank(current) > rank(best["metrics"])):
            best = dict(teams=[t[:] for t in teams], metrics=current, seed=seed)
        if len(teams) == 1:
            break
        temperature = 8
        for _ in range(iterations):
            if time.monotonic() >= deadline:
                break
            candidate = [t[:] for t in teams]
            a, b = rng.sample(range(len(teams)), 2)
            ia, ib = rng.randrange(len(candidate[a])), rng.randrange(len(candidate[b]))
            candidate[a][ia], candidate[b][ib] = candidate[b][ib], candidate[a][ia]
            ev = evaluate(model, candidate, reference)
            if not ev["hardConstraintsOk"]:
                continue
            delta = scalar(ev) - scalar(current)
            if delta >= 0 or rng.random() < math.exp(delta / max(temperature, .05)):
                teams, current = candidate, ev
            temperature *= .997
            if best is None or rank(current) > rank(best["metrics"]):
                best = dict(teams=[t[:] for t in teams], metrics=current, seed=seed)
        if time.monotonic() >= deadline:
            break
    if best is None:
        raise ValueError("No se encontró una solución que respete NO JUNTAR. Revisa las restricciones o prueba otra distribución.")
    return best
