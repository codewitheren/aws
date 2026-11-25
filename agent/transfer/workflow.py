"""Run transfer jobs in separate processes against immutable input snapshots."""
import csv
from hashlib import sha256
from datetime import datetime
import json
from pathlib import Path
import shutil
import sys
from zoneinfo import ZoneInfo

import pandas as pd

import calistir as engine
import gsheet_kaynak as sheets
from preflight import (CAMPAIGN, CATEGORIES, finding, grouped_changes, input_checks, parameter_checks,
                       relex_anomalies, relex_path, volume_load)
from analytics import compare_scenario, metrics, query
from scenarios import apply_changes, edit_scenario
import surucu

ORDER = ("girdi-kontrolu", "parametre-takibi", "relex-anomali", "hacim-yuku")


def run_motor(root, snapshot, kind, day, center, label, params=None):
    result = engine.calistir(kind, day, str(root / label), param=params, kaynak=f"yerel:{snapshot}", sessiz=True)
    if not result["ok"] or not result.get("allpl_ok"):
        detail = result.get("hata") or result.get("allpl_hata")
        raise ValueError(f"Motor veya All PL doğrulaması başarısız. {detail or 'Motor çıktısı eksik.'}")
    if result["merkez"] != center:
        raise ValueError(f"Seçilen merkez {center}, motorda tespit edilen merkez {result['merkez']}.")
    report = Path(result["klasor"]) / "sonuc.json"
    return result, report, pd.read_parquet(result["parquet"])


def motor_hash(kind):
    code = getattr(surucu, surucu.URUNLER[kind]["motor"]).encode()
    files = [Path(module.__file__).read_bytes() for module in (engine, surucu, sheets)]
    return sha256(b"\0".join([code, *files])).hexdigest()


def check_motor(job):
    if job.get("motorHash") and job["motorHash"] != motor_hash(job["kind"]):
        raise ValueError("Motor sürümü değişti. Aynı motorla karşılaştırma için yeni inceleme başlatın.")


def prepare(root, job):
    snapshot = root / "snapshot"
    kind, center, day = job["kind"], job["center"], job["date"]
    if not snapshot.is_dir():
        sheets.yerel_kopya_al(str(snapshot), [kind], log=lambda *_: None)
        if kind == "ms":
            # MS needs this list for the pre-run review, while its motor does not read it.
            (snapshot / "sheets" / str(CAMPAIGN)).write_bytes(sheets.csv_indir(CAMPAIGN))
    relex = pd.read_excel(relex_path(snapshot, kind), dtype={"Location code": str, "Product code": str})
    checks = input_checks(snapshot, kind, day, relex)
    if not any(c["level"] == "hata" for c in checks):
        detected = surucu.merkez_tespit(relex, CATEGORIES[kind])
        if detected["tespit"] != center or detected["pay"] < surucu.MERKEZ_ESIK:
            checks.insert(0, finding("girdi-kontrolu", "hata", "Relex merkezi uyuşmuyor",
                f"Seçilen merkez {center}. Dosyada tespit edilen merkez {detected['tespit'] or 'belirsiz'}.",
                relex_path(snapshot, kind).name + " / Location code"))
    draft, limits = None, []
    if not any(c["level"] == "hata" for c in checks):
        checks.extend(parameter_checks(snapshot, kind, center, day, relex))
        proposals, notes = relex_anomalies(snapshot, kind, center, day, relex)
        checks.extend(notes)
        checks.extend(grouped_changes(proposals, "relex-anomali",
            relex_path(snapshot, kind).name + f" / Effective quantity, 14 Days Sales, Daily FC; Kampanya / {CAMPAIGN}"))
        result, report, frame = run_motor(root, snapshot, kind, day, center, "taslak")
        limits = json.loads(report.read_text())["ozet"]["merkez"]
        draft = result["parquet"]
        checks.extend(grouped_changes(volume_load(snapshot, kind, frame, relex), "hacim-yuku",
            "Taslak motor parquet / önerilen hacim, dolap kapasitesi; Relex / satış ve stok"))
    checks.sort(key=lambda c: (ORDER.index(c["phase"]), {"hata": 0, "uyari": 1, "bilgi": 2}[c["level"]],
                               not c.get("hasLiters"), -c.get("score", 0)))
    for index, check in enumerate(checks):
        check["id"] = str(index + 1)
    return dict(rows=len(relex), checks=checks, blocked=any(c["level"] == "hata" for c in checks),
                draft=draft, draftLimits=limits, motorHash=motor_hash(kind))


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(columns)
        writer.writerows(rows)


def active_input(root, job):
    source = root / "snapshot"
    changes = job.get("revisions", [])
    if not changes:
        return source
    revised = root / "girdi_revize"
    shutil.copytree(source, revised)
    apply_changes(revised, job["kind"], changes)
    return revised


def finish(root, job):
    check_motor(job)
    kind, day, center = job["kind"], job["date"], job["center"]
    source = active_input(root, job)
    result, report_path, frame = run_motor(root, source, kind, day, center, "resmi")
    report = json.loads(report_path.read_text())
    stats = metrics(kind, frame)
    alerts = [dict(level=c["durum"], name=c["ad"], evidence=c["ozet"]) for c in report["kontrol"]
              if c["durum"] in ("hata", "uyari", "bilgi")]
    if "Cut_Priority" in frame:
        original, final = frame["Orijinal_Miktar"], frame["Final_Miktar"]
        invalid = frame[frame["Cut_Priority"].eq(101) & final.lt(original) & ~frame["Sayim_Kisiti"].eq(True)]
        if not invalid.empty:
            examples = ", ".join(f"{row['Location name']} · {row['Product name']} · {original[i]:g} → {final[i]:g} adet"
                                 for i, row in invalid.head(5).iterrows())
            alerts.append(dict(level="hata", name="Demirbaş kesimi", evidence=f"{len(invalid)} satır. {examples}"))
    write_csv(root / "uyarilar.csv", ["Seviye", "Kontrol", "Kanıt"], [a.values() for a in alerts])
    findings = [edit for check in job["checks"] for edit in check.get("edits", [])]
    revisions = job["revisions"]
    keys = lambda row: tuple(row[c].lower().strip() for c in ("depotCode", "productCode"))
    revised_values = {keys(r): r["value"] for r in revisions}
    write_csv(root / "anomaliler.csv", ["Kontrol", "Depo", "Ürün", "Kanıt", "Orijinal değer", "Koşu değeri"],
        [[f["reason"], f["depot"], f["product"], f["evidence"], f["current"], revised_values.get(keys(f), f["current"])]
         for f in findings])
    changed = []
    if revisions:
        final_column = "Final_Quantity" if kind == "ms" else "Final_Miktar"
        final_values = {tuple(str(k).lower().strip() for k in row[:2]): float(row[2])
            for row in frame[["Location code", "Product code", final_column]].itertuples(index=False, name=None)}
        now = datetime.now(ZoneInfo("Europe/Istanbul")).isoformat()
        write_csv(root / "revize_log.csv",
            ["zaman", "kategori", "depo_kodu", "depo_adi", "urun_kodu", "urun_adi", "eski_miktar", "yeni_miktar",
             "batch", "neden", "kanit", "onay"],
            [[now, kind, r["depotCode"], r["depot"], r["productCode"], r["product"], r["current"], r["value"],
              r["batch"], r["reason"], r["evidence"], r["approval"]] for r in revisions])
        changed = [dict(depot=r["depot"], product=r["product"], unit=r["unit"], original=r["current"],
                        revised=r["value"], final=final_values.get(keys(r))) for r in revisions]
    summary = dict(center=center, date=day, kind=kind, suggested=stats["proposedRows"], sent=stats["createdRows"],
        cp=stats["cpPct"], cut={unit: v["cutPct"] for unit, v in stats["quantities"].items() if v["cutPct"] is not None},
        primary={unit: v["reasons"][:1] for unit, v in stats["quantities"].items() if v["reasons"]},
        limits=report["ozet"]["merkez"], alerts=alerts, applied=len(revisions), reviewed=len(job["reviewed"]), revised=changed)
    files = {"transfer.xlsx": result["excel"], "transfer.parquet": result["parquet"], "allpl.parquet": result["allpl_parquet"],
        "allpl.xlsx": result["allpl_xlsx"], "sonuc.json": str(report_path), "uyarilar.csv": str(root / "uyarilar.csv"),
        "anomaliler.csv": str(root / "anomaliler.csv")}
    if revisions:
        files["revize_log.csv"] = str(root / "revize_log.csv")
    return dict(summary=summary, files=files, depots=report["detay"]["depolar"])


def scenario(root, job):
    check_motor(job)
    source = active_input(root, job)
    copy = root / "whatif" / "girdi"
    shutil.copytree(source, copy)
    kind, center, day = job["kind"], job["center"], job["date"]
    edits = job["change"] if isinstance(job["change"], list) else [job["change"]]
    changes, params, scopes = [], {}, []
    for edit in edits:
        change, current_params, scope = edit_scenario(copy, kind, day, edit)
        changes.append(change)
        params.update(current_params)
        if scope and scope not in scopes:
            scopes.append(scope)
    baseline = pd.read_parquet(root / "baseline.parquet")
    output, report, simulated = run_motor(root, copy, kind, day, center, "whatif", params)
    limits = {"before": job.get("summary", {}).get("limits", job.get("draftLimits", [])),
              "after": json.loads(report.read_text())["ozet"]["merkez"]}
    result = compare_scenario(kind, baseline, simulated, scopes[0] if len(scopes) == 1 else {})
    if len(scopes) > 1:
        result["targets"] = [dict(before=query(kind, baseline, **scope, why=True),
                                  after=query(kind, simulated, **scope, why=True)) for scope in scopes]
    files = {"transfer.parquet": output["parquet"], "sonuc.json": str(report)}
    return dict(changes=changes, limits=limits, files=files, **result)


def main():
    root = Path(sys.argv[1])
    job = json.loads((root / "job.json").read_text())
    handlers = {"prepare": prepare, "finish": finish, "scenario": scenario}
    result = handlers[job["action"]](root, job)
    (root / "result.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError) as exc:
        Path(sys.argv[1], "error.txt").write_text(str(exc)[:600])
        raise
