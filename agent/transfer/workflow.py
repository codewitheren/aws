"""Run transfer jobs in separate processes against immutable input snapshots."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from hashlib import sha256
from datetime import datetime
import json
import re
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pandas as pd

import calistir as engine
import gsheet_kaynak as sheets
from preflight import (CAMPAIGN, CATEGORIES, finding, grouped_changes, input_checks, iqr_outliers, parameter_checks,
                       relex_anomalies, relex_path, volume_load)
from analytics import compare_scenario, metrics, query
from scenarios import apply_changes, edit_scenario
from run_activity import PREFIX, activity, count
import surucu

ORDER = ("girdi-kontrolu", "parametre-takibi", "relex-anomali", "relex-aykiri", "hacim-yuku")
MOTOR_FILE = {"amb": "Ambient_Su.py", "cold": "Cold.py", "ms": "MS.py"}


def quiet(*args, **kwargs):
    pass


def worker_activity(*args, **kwargs):
    print(PREFIX + json.dumps(activity(*args, **kwargs)), flush=True)


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


def download_input_snapshot(snapshot, kind, emit=quiet):
    csv_tabs = {gid: name for name, gid in sheets.SHEET_SEKMELERI[kind].values()}
    if kind == "ms":
        # MS needs this list for the pre-run review, while its motor does not read it.
        csv_tabs[CAMPAIGN] = "Dokunulmayacak Ürünler (Kampanya)"
    xlsx_tabs = sheets.ELLE_SEKMELER[kind]

    def save(fetch, gid, target):
        return target.write_bytes(fetch(gid))

    emit("command", "Google Sheet sekmeleri isteniyor",
         f"{len(csv_tabs)} CSV ve {len(xlsx_tabs)} Excel sekmesi", "download_input_snapshot()")
    with TemporaryDirectory(dir=snapshot.parent) as directory:
        staging = Path(directory) / "snapshot"
        csv_dir, xlsx_dir = staging / "sheets", staging / "xlsx"
        csv_dir.mkdir(parents=True)
        xlsx_dir.mkdir()
        with ThreadPoolExecutor(max_workers=4) as pool:
            downloads = {pool.submit(save, sheets.csv_indir, gid, csv_dir / str(gid)): (name, "CSV")
                         for gid, name in csv_tabs.items()}
            downloads.update({pool.submit(save, sheets.xlsx_indir, gid, xlsx_dir / sheets.dosya_adi(name)): (name, "XLSX")
                              for name, gid in xlsx_tabs.values()})
            for download in as_completed(downloads):
                name, extension = downloads[download]
                size = download.result()
                emit("data", forecast_name(name), f"{extension} · {count(size)} bayt alındı")
        staging.rename(snapshot)


def prepare(root, job, emit=quiet):
    snapshot = root / "snapshot"
    kind, center, day = job["kind"], job["center"], job["date"]
    if not snapshot.is_dir():
        download_input_snapshot(snapshot, kind, emit)
    emit("command", "Forecast çalışma kopyası açılıyor", code="pandas.read_excel(...)")
    relex = pd.read_excel(relex_path(snapshot, kind), dtype={"Location code": str, "Product code": str})
    emit("data", "Forecast tablosu belleğe alındı", f"{count(len(relex))} satır · {count(len(relex.columns))} sütun")
    emit("command", "Girdi doğrulaması başlatıldı",
         f"{center} · {day} · güncellik, kategori, depo × ürün ve sipariş katı", "input_checks()")
    checks = input_checks(snapshot, kind, day, relex)
    if not any(c["level"] == "hata" for c in checks):
        detected = surucu.merkez_tespit(relex, CATEGORIES[kind])
        if detected["tespit"] != center or detected["pay"] < surucu.MERKEZ_ESIK:
            checks.insert(0, finding("girdi-kontrolu", "hata", "Relex merkezi uyuşmuyor",
                f"Seçilen merkez {center}. Dosyada tespit edilen merkez {detected['tespit'] or 'belirsiz'}.",
                relex_path(snapshot, kind).name + " / Location code"))
    draft, limits = None, []
    critical = [c for c in checks if c["level"] == "hata"]
    if critical:
        emit("check", "Girdiler koşuyu durdurdu", " · ".join(forecast_name(c["title"]) for c in critical))
    else:
        emit("check", "Girdiler doğrulandı", f"Merkez eşleşti · {count(len(checks))} girdi bulgusu")
        emit("command", "Parametreler geçmişle karşılaştırılıyor",
             "Kapasite, sayım, teslimat ve kategoriye özel kurallar", "parameter_checks()")
        parameters = parameter_checks(snapshot, kind, center, day, relex)
        checks.extend(parameters)
        emit("check", "Parametre karşılaştırması tamamlandı", f"{count(len(parameters))} bulgu")
        emit("command", "Öneriler satış ve benzer depolarla karşılaştırılıyor",
             "14 günlük satış, günlük tahmin, sipariş katı ve aynı ürünün G10/GB dağılımı",
             "relex_anomalies() → iqr_outliers()")
        proposals, notes = relex_anomalies(snapshot, kind, center, day, relex)
        # The demand-backed rule above is strict; also offer the peer-median (IQR) outliers, once per depot × product,
        # in their own phase so the demand-backed findings stay first.
        seen = {(p["depotCode"].strip().lower(), p["productCode"].strip().lower()) for p in proposals}
        peers = [p for p in iqr_outliers(snapshot, kind, relex)
                 if (p["depotCode"].strip().lower(), p["productCode"].strip().lower()) not in seen]
        checks.extend(notes)
        checks.extend(grouped_changes(proposals, "relex-anomali",
            relex_path(snapshot, kind).name + f" / Effective quantity, 14 Days Sales, Daily FC; Kampanya / {CAMPAIGN}"))
        checks.extend(grouped_changes(peers, "relex-aykiri",
            relex_path(snapshot, kind).name + " / Effective quantity, Order batch size (aynı ürün, aynı depo tipi)"))
        emit("check", "Öneri karşılaştırması tamamlandı",
             f"Satış ve tahminden {count(len(proposals))}, depo dağılımından {count(len(peers))} satır adayı")
        emit("command", "Taslak motor başlatıldı", "Girdi kopyasındaki özgün miktarlarla hesaplanıyor",
             f'{MOTOR_FILE[kind]} · run_motor(label="taslak")')
        result, report, frame = run_motor(root, snapshot, kind, day, center, "taslak")
        limits = json.loads(report.read_text())["ozet"]["merkez"]
        draft = result["parquet"]
        emit("output", "Taslak Parquet üretildi",
             f"{count(len(frame))} satır · merkez ve All PL doğrulandı")
        emit("command", "Taslak hacim yükü değerlendiriliyor",
             "Önerilen hacim, dolap kapasitesi, satış ve stok", "volume_load()")
        volume = volume_load(snapshot, kind, frame, relex)
        checks.extend(grouped_changes(volume, "hacim-yuku",
            "Taslak motor parquet / önerilen hacim, dolap kapasitesi; Relex / satış ve stok"))
        emit("check", "Hacim kontrolü tamamlandı", f"{count(len(volume))} satır adayı")
    checks.sort(key=lambda c: (ORDER.index(c["phase"]), {"hata": 0, "uyari": 1, "bilgi": 2}[c["level"]],
                               not c.get("hasLiters"), -c.get("score", 0)))
    for index, check in enumerate(checks):
        check["id"] = str(index + 1)
    blocked = any(c["level"] == "hata" for c in checks)
    if not blocked:
        warnings = sum(c["level"] == "uyari" for c in checks)
        emit("check", "İnceleme bulguları hazır", f"{count(warnings)} uyarı · {count(len(checks) - warnings)} bilgi")
    return dict(rows=len(relex), checks=checks, blocked=blocked,
                draft=draft, draftLimits=limits, motorHash=motor_hash(kind))


def forecast_name(value):
    # The engine calls the demand forecast source "Relex"; users know it as Forecast.
    if not isinstance(value, str):
        return value
    value = re.sub(r"Relex['’]te", "Forecast'ta", value)
    value = re.sub(r"Relex['’]e\b", "Forecast'a", value)
    value = re.sub(r"Relex['’]in\b", "Forecast'un", value)
    return value.replace("Relex", "Forecast").replace("relex", "forecast")


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow([forecast_name(c) for c in columns])
        writer.writerows([forecast_name(v) for v in row] for row in rows)


def screen_view(report):
    """Depot table, reasons, check cards and per-depot evidence for the web screens (read via view/depot)."""
    depots = report["detay"]["depolar"]
    lines = report["detay"]
    cols = lines["kolonlar"]
    pick = [cols.index(c) for c in ("Depo", "Ürün", "Öneri", "Final", "Kesilen", "Neden")]
    # MS depot table counts units only; bulk (Dökme) rows are in kg and stay out, as in depo_tablo.
    kind_col = cols.index("Tür") if "Tür" in cols else None
    per_depot = {}
    for values in lines["satirlar"]:
        if kind_col is not None and values[kind_col] == "Dökme":
            continue
        depot, product, suggested, final, cut, reason = (values[i] for i in pick)
        if cut and cut > 0:
            per_depot.setdefault(str(depot), []).append((product, suggested, final, cut, reason))
    for depot, rows in per_depot.items():
        entry = depots.setdefault(depot, {})
        reasons = {}
        for *_, cut, reason in rows:
            reasons[reason or "Diğer"] = reasons.get(reason or "Diğer", 0) + cut
        entry["nedenler"] = [{"ad": k, "kes": v} for k, v in sorted(reasons.items(), key=lambda x: -x[1])]
        top = sorted(rows, key=lambda r: -r[3])[:10]
        entry["urunler"] = [dict(urun=p, oneri=s, final=f, kesilen=c, neden=r) for p, s, f, c, r in top]

    def full_fill(entry):
        # Doluluk if everything proposed had been sent, worst cabinet first.
        rates = [100 * sum(d.get(k) or 0 for k in ("dolu", "fin", "kes")) / d["tavan"]
                 for d in entry.get("doluluk", []) if d.get("birim") == "L" and d.get("tavan")]
        return round(max(rates), 1) if rates else None
    fills = {name: full_fill(entry) for name, entry in depots.items()}
    view = dict(doluluk={k: v for k, v in fills.items() if v is not None}, tablo=report["depo_tablo"],
                nedenler=report["ozet"]["nedenler"], kartlar=report["oneri"].get("kartlar", []),
                sayi=report["oneri"].get("sayi", 0))
    return depots, view


def active_input(root, job):
    source = root / "snapshot"
    changes = job.get("revisions", [])
    if not changes:
        return source
    revised = root / "girdi_revize"
    shutil.copytree(source, revised)
    apply_changes(revised, job["kind"], changes)
    return revised


def finish(root, job, emit=quiet):
    check_motor(job)
    kind, day, center = job["kind"], job["date"], job["center"]
    source = active_input(root, job)
    revisions = job["revisions"]
    emit("data", "Resmi motor girdisi hazır",
         f"{count(len(revisions))} satıra onaylı miktar yazıldı" if revisions else "Özgün miktarlar kullanılıyor",
         "apply_changes()" if revisions else None)
    emit("command", "Resmi motor başlatıldı", f"{center} · {day}", f'{MOTOR_FILE[kind]} · run_motor(label="resmi")')
    result, report_path, frame = run_motor(root, source, kind, day, center, "resmi")
    emit("output", "Resmi Excel ve Parquet üretildi",
         f"{count(len(frame))} Parquet satırı · merkez ve All PL doğrulandı")
    emit("command", "Motor çıktısı denetleniyor",
         "Gönderim satırları, kısma nedenleri, limitler ve kategori kontrolleri", "metrics()")
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
    keys = lambda row: tuple(row[c].lower().strip() for c in ("depotCode", "productCode"))
    revised_values = {keys(r): r["value"] for r in revisions}
    write_csv(root / "anomaliler.csv", ["Kontrol", "Depo", "Ürün", "Kanıt", "Orijinal değer", "Optimizasyon değeri"],
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
    depots, view = screen_view(report)
    critical = sum(a["level"] == "hata" for a in alerts)
    warnings = sum(a["level"] == "uyari" for a in alerts)
    emit("check", "Çıktı denetimi tamamlandı",
         f"{count(stats['createdRows'])} gönderim satırı · {count(critical)} kritik · {count(warnings)} uyarı")
    return dict(summary=summary, files=files, depots=depots, view=view)


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
    handlers = {"prepare": prepare, "finish": finish}
    if job["action"] == "scenario":
        result = scenario(root, job)
    else:
        result = handlers[job["action"]](root, job, worker_activity)
    (root / "result.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError) as exc:
        Path(sys.argv[1], "error.txt").write_text(str(exc)[:600])
        raise
