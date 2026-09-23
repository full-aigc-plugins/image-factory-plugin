#!/usr/bin/env python3
"""Rebuild deterministic review summaries from verified receipts and scores."""

from __future__ import annotations

import html
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import quote

import artifact_collector
import atomic_json


SCHEMA_VERSION = "1.1.0"


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".summary-", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _verified_artifact(destination_dir: Path, receipt: dict) -> Path:
    destination = Path(destination_dir).resolve()
    target = (destination / receipt["path"]).resolve()
    if target != destination and destination not in target.parents:
        raise ValueError(f"receipt artifact path escapes destination: {receipt['path']!r}")
    errors = artifact_collector.verify_receipt(receipt, target)
    if errors:
        raise ValueError(f"receipt artifact verification failed: {'; '.join(errors)}")
    return target


def _region_markup(findings: list[dict]) -> str:
    boxes = []
    for finding in findings:
        region = finding.get("region")
        if region is None:
            continue
        x, y, width, height = (float(region[key]) for key in ("x", "y", "width", "height"))
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < width <= 1 - x and 0 < height <= 1 - y):
            continue
        boxes.append(
            f'<span class="region" title="{html.escape(finding["dimension"])}" '
            f'style="left:{x * 100:.2f}%;top:{y * 100:.2f}%;width:{width * 100:.2f}%;height:{height * 100:.2f}%"></span>'
        )
    return "".join(boxes)


def build_summary(
    *, receipts: dict[str, dict], scores: dict, destination_dir: Path, output_dir: Path,
    anchors: dict[str, str] | None = None,
) -> dict:
    """Write an HTML contact sheet and JSON storyboard without copying originals."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    anchors = anchors or {}
    if set(anchors) - set(receipts) or any(anchor not in receipts for anchor in anchors.values()):
        raise ValueError("anchor mappings must name verified receipt items")
    verified = {item_id: _verified_artifact(Path(destination_dir), receipt) for item_id, receipt in receipts.items()}
    gates = {
        row["item_id"]: row
        for row in scores.get("deterministic_gates", {}).get("per_item", [])
    }
    advisory = {
        row["item_id"]: row for row in scores.get("advisory", {}).get("items", [])
    }
    labels = {row["item_id"]: row for row in scores.get("human_labels", [])}
    findings: dict[str, list[dict]] = {}
    for report in scores.get("reviewer_reports", []):
        reviewer = report.get("reviewer") or {}
        for item in report.get("items", []):
            for finding in item.get("findings", []):
                findings.setdefault(item["item_id"], []).append({
                    "dimension": finding["dimension"],
                    "score": finding["score"],
                    "confidence": finding["confidence"],
                    "evidence": finding["evidence"],
                    "region": finding.get("region"),
                    "uncertain": finding["uncertain"],
                    "source": {"reviewer_id": reviewer.get("id"), "reviewer_version": reviewer.get("version")},
                })
    rows: list[dict] = []
    html_cards: list[str] = []
    for item_id in sorted(receipts):
        receipt = receipts[item_id]
        artifact = verified[item_id]
        relative = Path(os.path.relpath(artifact, output)).as_posix()
        anchor_id = anchors.get(item_id)
        anchor_relative = None if anchor_id is None else Path(os.path.relpath(verified[anchor_id], output)).as_posix()
        gate = gates.get(item_id, {})
        advisory_row = advisory.get(item_id)
        label = labels.get(item_id, {"label": "unlabeled"})
        row = {
            "item_id": item_id,
            "artifact_id": receipt["artifact_id"],
            "path": receipt["path"],
            "sha256": receipt["sha256"],
            "width": receipt["width"],
            "height": receipt["height"],
            "deterministic_passed": bool(gate.get("passed", False)),
            "failures": list(gate.get("failures") or []),
            "advisory_score": None if advisory_row is None else advisory_row.get("score"),
            "human_label": label.get("label", "unlabeled"),
            "human_reason": label.get("reason"),
            "anchor_item_id": anchor_id,
            "anchor_sha256": None if anchor_id is None else receipts[anchor_id]["sha256"],
            "findings": findings.get(item_id, []),
            "advisory_dimensions": list((advisory_row or {}).get("dimensions") or []),
            "dimensions": sorted({d["name"] for d in (advisory_row or {}).get("dimensions", [])} | {f["dimension"] for f in findings.get(item_id, [])}),
        }
        disagreements = []
        if row["human_label"] in ("approved", "rejected"):
            signals = [
                (finding["dimension"], finding["score"], finding["source"]["reviewer_id"])
                for finding in row["findings"] if not finding["uncertain"]
            ]
            signals.extend(
                (dimension["name"], dimension["score"], "advisory")
                for dimension in row["advisory_dimensions"] if dimension.get("complete", False)
            )
            for dimension, score, source in signals:
                predicted = "approved" if float(score) >= float(scores["pass_threshold"]) else "rejected"
                if predicted != row["human_label"]:
                    disagreements.append({"dimension": dimension, "source": source, "signal_label": predicted, "human_label": row["human_label"]})
        row["disagreements"] = disagreements
        rows.append(row)
        failures = ", ".join(row["failures"]) or "none"
        score_text = "n/a" if row["advisory_score"] is None else str(row["advisory_score"])
        anchor_html = (
            '<figure class="image-panel"><figcaption>基准帧 · ' + html.escape(anchor_id) + '</figcaption>'
            + f'<img src="{html.escape(quote(anchor_relative, safe="/.:_-"))}" alt="{html.escape(anchor_id)}"></figure>'
            if anchor_relative is not None else ''
        )
        finding_html = ''.join(
            '<li class="finding ' + ('uncertain' if finding['uncertain'] else 'difference' if finding['score'] < scores['pass_threshold'] else 'aligned') + '">'
            + '<strong>' + html.escape(finding['dimension']) + '</strong> · '
            + html.escape(str(finding['evidence'])) + ' · '
            + html.escape(str(finding['source']['reviewer_id'])) + '@' + html.escape(str(finding['source']['reviewer_version']))
            + (' · 区域 ' + html.escape(', '.join(f'{key}={value}' for key, value in finding['region'].items())) if finding['region'] else '')
            + (' · 不确定' if finding['uncertain'] else '') + '</li>'
            for finding in row['findings']
        )
        advisory_html = ''.join(
            '<li>advisory · ' + html.escape(str(dimension['name']))
            + ' · score=' + html.escape(str(dimension['score']))
            + ' · ' + html.escape(str(dimension.get('evidence', '')))
            + (' · 证据不完整' if not dimension.get('complete', False) else '') + '</li>'
            for dimension in row['advisory_dimensions']
        )
        disagreement_html = ''.join(
            '<li class="difference">人工/自动分歧 · ' + html.escape(entry['dimension'])
            + ' · ' + html.escape(str(entry['source'])) + '→' + html.escape(entry['signal_label'])
            + ' / 人工→' + html.escape(entry['human_label']) + '</li>'
            for entry in disagreements
        )
        html_cards.append(
            f'<article class="card" data-item-id="{html.escape(item_id)}" data-dimensions="{html.escape(" ".join(row["dimensions"]))}">'
            '<div class="compare">' + anchor_html + '<figure class="image-panel"><figcaption>当前帧</figcaption>'
            '<div class="image-wrap">'
            f'<img src="{html.escape(quote(relative, safe="/.:_-"))}" alt="{html.escape(item_id)}">'
            + _region_markup(row['findings']) + '</div></figure></div>'
            f"<h2>{html.escape(item_id)}</h2>"
            f"<p>{receipt['width']}x{receipt['height']} · gate={str(row['deterministic_passed']).lower()}</p>"
            f"<p>failures={html.escape(failures)} · advisory={html.escape(score_text)} "
            f"· human={html.escape(str(row['human_label']))}</p>"
            f'<ul class="findings">{finding_html}{advisory_html}{disagreement_html}</ul>'
            '<fieldset><legend>人工决定（仅导出草稿，不自动写入任务台账）</legend>'
            '<label><input type="radio" name="decision-' + html.escape(item_id) + '" value="approved"' + (' checked' if row['human_label'] == 'approved' else '') + '>接受</label>'
            '<label><input type="radio" name="decision-' + html.escape(item_id) + '" value="rejected"' + (' checked' if row['human_label'] == 'rejected' else '') + '>拒绝</label>'
            '<label>理由<textarea name="review-reason" rows="2" placeholder="指出人物或元素差异">' + html.escape(str(row['human_reason'] or '')) + '</textarea></label></fieldset>'
            f"<code>{html.escape(receipt['sha256'])}</code>"
            "</article>"
        )

    index = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": scores["batch_id"],
        "round": scores["round"],
        "decision": scores["decision"],
        "items": rows,
    }
    index_path = output / "storyboard.json"
    atomic_json.write_json_atomic(index_path, index)
    contact_path = output / "contact-sheet.html"
    _write_text_atomic(
        contact_path,
        "<!doctype html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Image Factory review</title><style>"
        "*{box-sizing:border-box}body{font-family:system-ui;margin:24px;background:#f5f5f2;color:#171717}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,400px),1fr));gap:16px}"
        ".card{min-width:0;background:white;border:1px solid #ddd;border-radius:12px;padding:14px}"
        ".compare{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}"
        ".image-panel{min-width:0;margin:0;background:#eee}.image-panel img{display:block;width:100%;height:auto}"
        ".image-wrap{position:relative}.region{position:absolute;border:2px solid #d45122;background:#d4512222;pointer-events:none}"
        "figcaption{padding:4px;font-size:13px}h2{font-size:18px}code{font-size:10px;overflow-wrap:anywhere}"
        "fieldset{border:1px solid #ccc;display:grid;gap:8px}label{display:block}textarea,select,button{max-width:100%;font:inherit}textarea{width:100%}"
        ".findings{padding-left:20px;overflow-wrap:anywhere}.difference{border-left:3px solid #c43;padding-left:6px}.uncertain{border-left:3px solid #d90;padding-left:6px}"
        "@media(max-width:390px){body{margin:12px}.grid,.compare{grid-template-columns:minmax(0,1fr)}.card{padding:10px}}"
        "</style></head><body>"
        f"<h1>{html.escape(str(scores['batch_id']))} · round {scores['round']}</h1>"
        f"<p>decision={html.escape(str(scores['decision']))}</p>"
        '<label>按维度筛选 <select name="dimension-filter" id="dimension-filter"><option value="">全部</option>'
        + ''.join(f'<option value="{html.escape(name)}">{html.escape(name)}</option>' for name in sorted({name for row in rows for name in row['dimensions']}))
        + '</select></label><button type="button" id="download-review">下载人工标注草稿</button>'
        + f'<main class="grid">{"".join(html_cards)}</main>'
        + '<script>const filter=document.getElementById("dimension-filter");'
        + 'filter.addEventListener("change",()=>document.querySelectorAll(".card").forEach(card=>{card.hidden=!!filter.value&&!card.dataset.dimensions.split(" ").includes(filter.value)}));'
        + 'document.getElementById("download-review").addEventListener("click",()=>{'
        + 'const rows=[...document.querySelectorAll(".card")].map(card=>({item_id:card.dataset.itemId,label:card.querySelector("input[type=radio]:checked")?.value??null,reason:card.querySelector("textarea").value})).filter(row=>row.label);'
        + 'const labels=Object.fromEntries(rows.map(row=>[row.item_id,{label:row.label,reason:row.reason}]));'
        + 'const blob=new Blob([JSON.stringify(labels,null,2)],{type:"application/json"});'
        + 'const link=document.createElement("a");link.href=URL.createObjectURL(blob);link.download="review-draft.json";link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000)});</script>'
        + '</body></html>\n',
    )
    return {
        "contact_sheet": str(contact_path),
        "storyboard_index": str(index_path),
    }
