"""Run one transfer job in an isolated process. Paths are owned by the runtime."""
import csv
import json
import math
import re
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

import calistir as engine
import gsheet_kaynak as sheets

CATEGORIES = {"amb": "Ambient ve Su", "cold": "+4", "ms": "MS"}


def relex_path(snapshot, kind):
    title, _ = sheets.ELLE_SEKMELER[kind]["relex"]
    return snapshot / "xlsx" / sheets.dosya_adi(title)


def inspect(snapshot, kind, center):
    frame = pd.read_excel(relex_path(snapshot, kind))
    import surucu

    detected = surucu.merkez_tespit(frame, CATEGORIES[kind])
    if detected["tespit"] != center or detected["pay"] < surucu.MERKEZ_ESIK:
        raise ValueError(f"Seçilen merkez {center}. Girdide tespit edilen merkez {detected['tespit'] or 'belirsiz'}.")
    qty = pd.to_numeric(frame["Effective quantity"], errors="raise")
    batch = pd.to_numeric(frame["Order batch size"], errors="coerce")
    domain = frame["Domain Type"].astype("string").str.strip().str.upper()
    product = frame["Product code"]
    depot = frame["Location code"]
    valid = domain.isin(["G10", "GB"]) & product.notna() & depot.notna()
    # Compare independent depots with exactly one proposal for the product.
    valid &= ~frame.duplicated(["Location code", "Product code"], keep=False)
    valid &= qty.ge(0) & ~frame["Transfer type"].astype(str).str.strip().str.upper().eq("BULK")
    groups = qty[valid].groupby([product[valid], domain[valid]])
    median = groups.transform("median")
    means = groups.transform("mean")
    q1 = groups.transform("quantile", q=.25)
    q3 = groups.transform("quantile", q=.75)
    spread = pd.concat([q3 - q1, .25 * median], axis=1).max(axis=1).clip(lower=1)
    limit = q3 + 1.5 * spread
    excluded = frame["Product name"].str.contains("beypazar", case=False, na=False)
    for col in ["Custom category", "Custom sub-category"]:
        excluded |= frame[col].str.contains("demirbaş|demirbas", case=False, na=False)
    if kind == "amb":
        water = pd.read_csv(snapshot / "sheets/1975210347")
        excluded |= product.astype(str).str.lower().isin(water["Product ID"].astype(str).str.lower())
    eligible = (groups.transform("count") >= 8) & qty.reindex(limit.index).gt(limit)
    rows = []
    for i in eligible.index[eligible]:
        if excluded[i] or not (qty[i] > batch[i] > 0):
            continue
        proposed = max(batch[i], math.floor(median[i] / batch[i]) * batch[i])
        if proposed < qty[i]:
            rows.append(dict(row=int(i + 2), depot=str(frame.at[i,"Location name"]),
                             product=str(frame.at[i,"Product name"]), domain=domain[i],
                             current=float(qty[i]), proposed=float(proposed), batch=float(batch[i]),
                             median=float(median[i]), mean=float(means[i]), limit=float(limit[i])))
    rows.sort(key=lambda item: item["current"] - item["proposed"], reverse=True)
    return dict(center=center, rows=len(frame), findings=rows, unknownDomain=int((~domain.isin(["G10","GB"])).sum()))


def forecast_name(value):
    # The engine calls the demand forecast source "Relex"; users know it as Forecast.
    if not isinstance(value, str):
        return value
    value = re.sub(r"Relex['’]te", "Forecast'ta", value)
    value = re.sub(r"Relex['’]e\b", "Forecast'a", value)
    value = re.sub(r"Relex['’]in\b", "Forecast'un", value)
    return value.replace("Relex", "Forecast")


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow([forecast_name(c) for c in columns])
        writer.writerows([forecast_name(v) for v in row] for row in rows)


def finish(root, job):
    kind = job["kind"]
    path = relex_path(root / "snapshot", kind)
    if job["changes"]:
        book = load_workbook(path)
        sheet = book.active
        column = [cell.value for cell in sheet[1]].index("Effective quantity") + 1
        for row, value in job["changes"].items():
            sheet.cell(int(row), column).value = value
        book.save(path)
        book.close()
    result = engine.calistir(kind, job["date"], str(root / "out"),
                             kaynak="yerel:" + str(root / "snapshot"), sessiz=True)
    if not result["ok"] or not result.get("allpl_ok") or result["merkez"] != job["center"]:
        raise ValueError("Motor veya All PL doğrulaması başarısız. Girdi ve merkez eşleşmesini kontrol edin.")
    report_path = Path(result["klasor"]) / "sonuc.json"
    report = json.loads(report_path.read_text())
    frame = pd.read_parquet(result["parquet"])
    original, final = (("Effective quantity","Final_Quantity") if kind == "ms" else ("Orijinal_Miktar","Final_Miktar"))
    suggested = int(frame[original].gt(0).sum())
    sent = int(frame[final].gt(0).sum())
    bulk = frame["Is_Bulk"].eq(True) if kind == "ms" else pd.Series(False, index=frame.index)
    rates = {}
    for unit, mask in [("adet", ~bulk), ("kg", bulk)]:
        portion = frame[mask & frame[original].gt(0)]
        if not portion.empty:
            rates[unit] = round(100 * (portion[original]-portion[final]).clip(lower=0).sum()/portion[original].sum(), 2)
    alerts = [dict(level=c["durum"], name=c["ad"], evidence=c["ozet"]) for c in report["kontrol"] if c["durum"] in ("hata","uyari","bilgi")]
    for card in report["oneri"].get("kartlar", []):
        if card.get("ozet"):
            alerts.append(dict(level="uyari", name=card["baslik"], evidence=card["ozet"]))
    if "Cut_Priority" in frame:
        invalid = frame[frame["Cut_Priority"].eq(101) & frame[final].lt(frame[original])
                        & ~frame["Sayim_Kisiti"].eq(True)]
        for _, row in invalid.iterrows():
            alerts.append(dict(level="hata", name="Demirbaş kesimi",
                evidence=f"{row['Location name']} · {row['Product name']} · {row[original]:g} → {row[final]:g} adet"))
    write_csv(root/"uyarilar.csv", ["Seviye","Kontrol","Kanıt"], [a.values() for a in alerts])
    findings = job["findings"]
    anomaly_rows = [["Depolar arası öneri", f["depot"], f["product"],
                     f'{f["domain"]} · öneri {f["current"]:g} · medyan {f["median"]:g} · üst sınır {f["limit"]:g}',
                     job["changes"].get(str(f["row"]), f["current"])] for f in findings]
    for card in report["oneri"].get("kartlar", []):
        table = card["tablo"]
        for values in table["satirlar"]:
            record = dict(zip(table["kolonlar"], values))
            evidence = " · ".join(f"{key} {value}" for key, value in record.items()
                                 if key not in ("Depo", "Ürün") and value is not None)
            anomaly_rows.append([card["baslik"], record.get("Depo"), record.get("Ürün"), evidence, ""])
    write_csv(root/"anomaliler.csv", ["Kontrol","Depo","Ürün","Kanıt","Koşu değeri"], anomaly_rows)
    limits = report["ozet"]["merkez"]
    summary = dict(center=job["center"], date=job["date"], kind=kind, suggested=suggested, sent=sent,
                   cp=round(100*sent/suggested,2) if suggested else None, cut=rates, limits=limits,
                   alerts=alerts, applied=len(job["changes"]), reviewed=len(findings))
    depots = report["detay"]["depolar"]
    lines = report["detay"]
    cols = lines["kolonlar"]
    pick = [cols.index(c) for c in ("Depo", "Ürün", "Öneri", "Final", "Kesilen", "Neden")]
    per_depot = {}
    # MS depot table counts units only; bulk (Dökme) rows are in kg and stay out, as in depo_tablo.
    kind_col = cols.index("Tür") if "Tür" in cols else None
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
    view = dict(doluluk={k: v for k, v in fills.items() if v is not None}, tablo=report["depo_tablo"], nedenler=report["ozet"]["nedenler"],
                kartlar=report["oneri"].get("kartlar", []), sayi=report["oneri"].get("sayi", 0))
    files = {"transfer.xlsx":result["excel"],"transfer.parquet":result["parquet"],"allpl.parquet":result["allpl_parquet"],
             "allpl.xlsx":result["allpl_xlsx"],"sonuc.json":str(report_path),"uyarilar.csv":str(root/"uyarilar.csv"),
             "anomaliler.csv":str(root/"anomaliler.csv")}
    return dict(summary=summary, files=files, depots=depots, view=view)


def main():
    root = Path(sys.argv[1])
    job = json.loads((root/"job.json").read_text())
    if job["action"] == "prepare":
        sheets.yerel_kopya_al(str(root/"snapshot"), [job["kind"]], log=lambda *_: None)
        result = inspect(root/"snapshot", job["kind"], job["center"])
    else:
        result = finish(root, job)
    (root/"result.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError) as exc:
        Path(sys.argv[1], "error.txt").write_text(str(exc)[:450])
        raise
