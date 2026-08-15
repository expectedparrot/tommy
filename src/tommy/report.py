from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from .errors import TommyError
from .store import Store, read_json


def _e(value: Any) -> str:
    return escape(str(value))


def _score(review: dict[str, Any], scorecard: dict[str, Any]) -> tuple[float, float, int]:
    maxima = {c["id"]: c["max_score"] for g in scorecard["groups"] for c in g["criteria"]}
    earned = sum(float(item["score"]) for item in review["criteria"])
    possible = sum(float(maxima[item["criterion_id"]]) for item in review["criteria"])
    percent = round(100 * earned / possible) if possible else 0
    return earned, possible, percent


def _evidence_links(items: list[dict[str, Any]]) -> str:
    return "".join(
        f'<a class="evidence" href="#{_e(item["turn_id"])}" data-turn="{_e(item["turn_id"])}">'
        f"{_e(item.get('label') or item['turn_id'])} ↗</a>"
        for item in items
    )


def render_report(
    project: dict[str, Any],
    template: dict[str, Any],
    practice: dict[str, Any],
    attempt: dict[str, Any],
    scorecard: dict[str, Any],
    review: dict[str, Any],
) -> str:
    earned, possible, percent = _score(review, scorecard)
    criteria = {item["criterion_id"]: item for item in review["criteria"]}
    turns = "".join(
        f'<article class="turn {"seller" if turn["role"] == "seller" else "buyer"}" id="{_e(turn["turn_id"])}">'
        f'<div class="turn-meta"><strong>{_e(turn["speaker"])}</strong><span>{_e(turn.get("timestamp") or "")}</span></div>'
        f"<p>{_e(turn['text'])}</p></article>"
        for turn in attempt["turns"]
    )
    recommendations = "".join(f"<li>{_e(item)}</li>" for item in review["recommendations"])
    strengths = "".join(f"<li>{_e(item)}</li>" for item in review["strengths"])
    groups = []
    for group in scorecard["groups"]:
        cards = []
        group_earned = sum(float(criteria[c["id"]]["score"]) for c in group["criteria"])
        group_possible = sum(float(c["max_score"]) for c in group["criteria"])
        for definition in group["criteria"]:
            item = criteria[definition["id"]]
            ratio = float(item["score"]) / definition["max_score"]
            state = "good" if ratio >= 0.8 else "mixed" if ratio >= 0.5 else "poor"
            cards.append(
                f'<details class="criterion"><summary><span class="criterion-state {state}"></span>'
                f"<span>{_e(definition['name'])}</span><b>{_e(item['score'])}/{definition['max_score']}</b></summary>"
                f'<div class="criterion-body"><p>{_e(item["explanation"])}</p>'
                f"{_evidence_links(item.get('evidence', []))}"
                f"<h4>Try instead</h4><p>{_e(item.get('better_response', 'No alternative supplied.'))}</p>"
                f"<small>Evaluator confidence: {_e(item.get('confidence', 'not reported'))}</small></div></details>"
            )
        groups.append(
            f'<section class="score-group"><header><h3>{_e(group["name"])}</h3>'
            f"<strong>{group_earned:g}/{group_possible:g}</strong></header>{''.join(cards)}</section>"
        )
    objections = (
        "".join(
            f'<details class="objection"><summary><span>{_e(item["category"])}</span>'
            f'<b class="resolution {"resolved" if item.get("resolved") else "unresolved"}">'
            f"{'Resolved' if item.get('resolved') else 'Unresolved'}</b></summary>"
            f"<div><p><strong>Buyer concern:</strong> {_e(item['buyer_concern'])}</p>"
            f"<p><strong>Assessment:</strong> {_e(item['assessment'])}</p>{_evidence_links(item.get('evidence', []))}"
            f"<p><strong>Better talk track:</strong> {_e(item.get('better_response', '—'))}</p></div></details>"
            for item in review["objections"]
        )
        or '<p class="empty">No objections were coded.</p>'
    )
    embedded = json.dumps({"attempt": attempt, "review": review}, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(attempt["rep"])} · {_e(template["name"])} · Tommy</title>
<style>
:root{{--ink:#17202a;--muted:#6b7280;--line:#dfe5eb;--panel:#fff;--canvas:#f4f7f9;--blue:#1576d4;--aqua:#daf5f3;--red:#df3838;--green:#16845b;--amber:#ca8010}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--canvas);color:var(--ink);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}
.top{{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid var(--line);padding:18px 28px;display:flex;align-items:center;gap:22px;flex-wrap:wrap}}
.brand{{font-weight:850;font-size:20px;letter-spacing:-.03em}}.meta{{display:flex;align-items:center;gap:10px;flex:1;flex-wrap:wrap}}.pill{{border:1px solid var(--line);padding:6px 11px;border-radius:999px;background:#fff}}.pill.buyer{{border-color:#57cce4}}.score{{display:flex;align-items:center;gap:9px;font-size:17px;font-weight:750}}.score-dot{{width:10px;height:10px;border-radius:50%;background:{"#29a36a" if percent >= 80 else "#e4a11b" if percent >= 60 else "#e53e3e"}}}
.layout{{display:grid;grid-template-columns:minmax(360px,44%) 1fr;gap:16px;max-width:1600px;margin:16px auto;padding:0 16px 28px}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:16px;box-shadow:0 1px 2px #18212b0a;overflow:hidden}}
.panel-head{{padding:17px 20px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between}}.panel-head h2{{font-size:17px;margin:0}}.transcript{{height:calc(100vh - 130px);position:sticky;top:96px;display:flex;flex-direction:column}}.turns{{overflow:auto;padding:18px}}
.turn{{max-width:82%;border:1px solid var(--line);border-radius:14px;margin:0 0 16px;padding:12px 14px;scroll-margin-top:125px;transition:.3s}}.turn.buyer{{background:#edf8f8;border-top-left-radius:4px}}.turn.seller{{margin-left:auto;background:#fff;border-top-right-radius:4px}}.turn:target,.turn.highlight{{outline:3px solid #f5b942;box-shadow:0 0 0 7px #f5b94230}}.turn-meta{{display:flex;justify-content:space-between;color:var(--muted);font-size:13px}}.turn p{{white-space:pre-wrap;margin:8px 0 0;font-size:16px}}
.tabs{{display:flex;border-bottom:1px solid var(--line);padding:0 22px;gap:24px;position:sticky;top:86px;background:#fff;z-index:3}}.tab{{appearance:none;border:0;background:transparent;padding:16px 3px;color:var(--muted);font-weight:700;cursor:pointer;border-bottom:3px solid transparent}}.tab.active{{color:var(--blue);border-color:var(--blue)}}.view{{display:none;padding:20px}}.view.active{{display:block}}
.hero{{border:1px solid var(--line);border-radius:15px;padding:22px;margin-bottom:18px}}.hero-top{{display:flex;align-items:center;gap:16px}}.badge{{width:64px;height:64px;border-radius:18px;background:{"#d8f3e6" if percent >= 80 else "#fff0cf" if percent >= 60 else "#ffe0e0"};color:{"#16845b" if percent >= 80 else "#a15c00" if percent >= 60 else "#bd2626"};display:grid;place-items:center;font-size:28px;font-weight:850}}h2,h3,h4{{line-height:1.25}}.hero h2{{margin:0}}.outcome{{color:var(--muted);margin:5px 0 0}}.columns{{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:18px}}ul{{padding-left:22px}}li{{margin:7px 0}}
.score-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.score-group{{border:1px solid var(--line);border-radius:13px;overflow:hidden}}.score-group>header{{display:flex;justify-content:space-between;padding:14px 16px;background:#fafbfc}}.score-group h3{{font-size:15px;margin:0}}details{{border-top:1px solid var(--line)}}summary{{list-style:none;cursor:pointer;padding:14px 16px;display:flex;align-items:center;gap:10px}}summary::-webkit-details-marker{{display:none}}summary b{{margin-left:auto}}.criterion-state{{width:11px;height:11px;border-radius:50%}}.criterion-state.good{{background:var(--green)}}.criterion-state.mixed{{background:var(--amber)}}.criterion-state.poor{{background:var(--red)}}.criterion-body,.objection>div{{padding:0 16px 16px;color:#3e4752}}.evidence{{display:inline-block;margin:4px 7px 4px 0;padding:4px 8px;border-radius:7px;background:#eaf3fd;color:#1264ad;text-decoration:none;font-size:13px}}.resolution{{font-size:12px;padding:3px 8px;border-radius:999px}}.resolved{{color:var(--green);background:#e3f6ed}}.unresolved{{color:#b12626;background:#ffe8e8}}.objection:first-child{{border-top:0}}small{{color:var(--muted)}}
@media(max-width:950px){{.layout{{grid-template-columns:1fr}}.transcript{{height:auto;position:static}}.turns{{max-height:650px}}.tabs{{top:83px}}}}@media(max-width:650px){{.top{{padding:14px}}.layout{{padding:0 8px}}.columns,.score-grid{{grid-template-columns:1fr}}.turn{{max-width:94%}}}}
@media print{{.top,.tabs{{position:static}}.layout{{display:block}}.transcript{{height:auto;position:static;margin-bottom:16px}}.turns{{overflow:visible}}.view{{display:block!important}}.tab{{display:none}}}}
</style></head><body>
<header class="top"><div class="brand">◆ tommy</div><div class="meta"><span>Rep <b>{_e(attempt["rep"])}</b></span><span>·</span><span class="pill buyer">Buyer <b>{_e(attempt["buyer"])}</b></span><span class="pill">{_e(template["call_type"])}</span><span class="pill">{_e(practice["settings"]["difficulty"])}</span></div><div class="score"><span class="score-dot"></span>{percent}/100 <small>({_e(earned):s}/{_e(possible):s})</small></div></header>
<main class="layout"><section class="panel transcript"><div class="panel-head"><h2>Transcript</h2><span>{len(attempt["turns"])} turns</span></div><div class="turns">{turns}</div></section>
<section class="panel"><nav class="tabs"><button class="tab active" data-view="feedback">Feedback</button><button class="tab" data-view="scorecard">Scorecard</button><button class="tab" data-view="objections">Objections</button></nav>
<div id="feedback" class="view active"><section class="hero"><div class="hero-top"><div class="badge">{percent}</div><div><h2>Recommendations from Tommy</h2><p class="outcome">{_e(review["outcome"])}</p></div></div><div class="columns"><div><h3>What to improve</h3><ul>{recommendations}</ul></div><div><h3>What went well</h3><ul>{strengths}</ul></div></div></section></div>
<div id="scorecard" class="view"><div class="score-grid">{"".join(groups)}</div></div><div id="objections" class="view">{objections}</div></section></main>
<script type="application/json" id="tommy-data">{embedded}</script><script>
document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{{document.querySelectorAll('.tab,.view').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.view).classList.add('active')}}));
document.querySelectorAll('.evidence').forEach(a=>a.addEventListener('click',()=>{{const t=document.getElementById(a.dataset.turn);document.querySelectorAll('.turn').forEach(x=>x.classList.remove('highlight'));if(t){{t.classList.add('highlight');setTimeout(()=>t.classList.remove('highlight'),3000)}}}}));
</script></body></html>"""


def generate_report(store: Store, attempt_id: str, output: Path | None = None) -> dict[str, Any]:
    attempt = store.get("attempts", attempt_id)
    practice = store.get("practices", attempt["practice_id"])
    template = store.get("templates", practice["template_id"])
    scorecard = store.get("scorecards", practice["scorecard_id"])
    review_path = store.base / "attempts" / attempt["id"] / "review.json"
    if not review_path.exists():
        raise TommyError("review_required", f"Attempt `{attempt_id}` has no registered review.")
    review = read_json(review_path)
    project = read_json(store.root / "tommy.json")
    target = output.resolve() if output else store.base / "attempts" / attempt["id"] / "report.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render_report(project, template, practice, attempt, scorecard, review), encoding="utf-8"
    )
    _, _, percent = _score(review, scorecard)
    return {"attempt_id": attempt["id"], "report": str(target), "score": percent, "standalone": True}
