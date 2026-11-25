"""Deterministic input validation and ordered, evidence-backed transfer review."""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import gsheet_kaynak as sheets
from surucu import _norm

CATEGORIES = {"amb": "Ambient ve Su", "cold": "+4", "ms": "MS"}
WEEKDAYS = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")
CAMPAIGN = 1527796592
WATER = 1975210347
BUFFER = 1173976478
SHARE = 2106866758
TRUCK = 670096216
WATER_SPACE = 868077377
OTHER_ETB = "Şarküteri ve Merkezden Giden ETB"
REQUIRED = {
    "Effective quantity", "Location code", "Product code", "Location name", "Product name",
    "Delivery date", "Order batch size", "Domain Type", "Daily FC", "Transfer type",
    "Custom category", "Custom sub-category", "14 Days Sales", "End balance", "Open purchase orders",
}


def relex_path(snapshot, kind):
    title, _ = sheets.ELLE_SEKMELER[kind]["relex"]
    return snapshot / "xlsx" / sheets.dosya_adi(title)


def table(snapshot, gid):
    return pd.read_csv(snapshot / "sheets" / str(gid), dtype=str).rename(columns=str.strip)


def domain(frame):
    return frame["Domain Type"].fillna("").astype(str).str.strip().str.upper().replace("", "GB")


def ids(series):
    return series.astype("string").str.strip().str.lower()


def numbers(series):
    return pd.to_numeric(series, errors="coerce").where(lambda v: np.isfinite(v))


def ratio(value):
    if pd.isna(value):
        return None
    text = str(value).strip().replace(",", ".")
    try:
        result = float(text.rstrip("%"))
    except ValueError:
        return None
    result = result / 100 if text.endswith("%") else result
    return result if np.isfinite(result) else None


def part(snapshot, gid, column):
    data = table(snapshot, gid)
    return dict(zip(data["Depo Adı"].dropna().map(_norm), data.loc[data["Depo Adı"].notna(), column].map(ratio)))


def finding(phase, level, title, evidence, source, **values):
    return dict(phase=phase, level=level, title=title, evidence=evidence, source=source, **values)


def input_checks(snapshot, kind, day, d):
    source = relex_path(snapshot, kind).name
    notes = []

    def add(level, title, evidence, origin=source, **values):
        notes.append(finding("girdi-kontrolu", level, title, evidence, origin, **values))

    missing = sorted(REQUIRED - set(d))
    if d.empty or missing:
        add("hata", "Relex boş veya eksik", "Eksik kolonlar: " + ", ".join(missing) if missing else "Dosyada satır yok.")
        return notes
    q, b = numbers(d["Effective quantity"]), numbers(d["Order batch size"])
    bulk = kind == "ms" and d["Transfer type"].eq("BULK")
    transfers = {"amb": {"AMBIENT"}, "cold": {"COLD_FOOD"}, "ms": {"FV", "BULK"}}
    if (~d["Transfer type"].isin(transfers[kind])).any() or (
        kind == "ms" and not d["Custom category"].eq("Meyve & Sebze").all()
    ):
        add("hata", "Relex kategorisi uyuşmuyor", "Seçilen kategoriye ait Relex sekmesini yükleyin.", source + " / Transfer type, Custom category")
    delivery = pd.to_datetime(d["Delivery date"], errors="coerce")
    invalid_date = delivery.isna() | delivery.lt(pd.Timestamp(day))
    if invalid_date.any():
        add("hata", "Teslimat tarihi eksik veya eski", f"{invalid_date.sum()} satır. İş gününe ait Relex dosyası gerekli.", source + " / Delivery date")
    multiples = q / b.where(b.gt(0))
    batch_error = ~np.isclose(multiples, multiples.round(), rtol=0, atol=1e-8)
    if kind == "ms":
        batch_error &= ~bulk
    invalid_qty = q.isna() | q.lt(0) | b.isna() | b.le(0) | batch_error
    if invalid_qty.any():
        add("hata", "Geçersiz öneri veya sipariş katı", f"{invalid_qty.sum()} satırda öneri boş, negatif veya sipariş katı geçersiz.", source + " / Effective quantity, Order batch size")
    keys = d[["Location code", "Product code"]].apply(ids)
    invalid_key = keys.duplicated(keep=False) | keys.isna().any(axis=1) | keys.eq("").any(axis=1)
    if invalid_key.any():
        add("hata", "Tekrarlı veya eksik depo × ürün", f"{invalid_key.sum()} satır.", source + " / Location code, Product code")
    wrong_domain = ~domain(d).isin(["G10", "GB"])
    if wrong_domain.any():
        add("hata", "Geçersiz depo tipi", f"{wrong_domain.sum()} satır G10 veya GB olarak tanımlanmalı.", source + " / Domain Type")

    fc_zero = q.gt(0) & numbers(d["Daily FC"]).fillna(0).le(0)
    if fc_zero.any():
        extra = ""
        if kind == "ms":
            extra = f" ({(fc_zero & ~bulk).sum()} paketli, {(fc_zero & bulk).sum()} dökme)"
        add("uyari", "Tahmin yokken öneri var", f"{fc_zero.sum()} satır{extra}, {keys.loc[fc_zero, 'Product code'].nunique()} ürün.", source + " / Daily FC, Effective quantity")

    volume_id, volume_key = (1615488785, "marketproduct_id") if kind == "amb" else (1098615637, "Product ID")
    missing_volume = q.gt(0) & ~keys["Product code"].isin(ids(table(snapshot, volume_id)[volume_key]).dropna())
    if missing_volume.any():
        add("uyari", "Ürün hacmi eksik", f"{keys.loc[missing_volume, 'Product code'].nunique()} ürün, {missing_volume.sum()} satır."
            + (" Motor 0,5 L kullanır." if kind == "amb" else ""), f"Sekme {volume_id} / {volume_key}")

    depots = dict(zip(d["Location name"].map(_norm), d["Location name"].astype(str)))
    capacity_id = 1473098648 if kind == "amb" else 108896607
    capacity = table(snapshot, capacity_id)
    if kind == "amb":
        stale = len(capacity) < 400
        freshness = f"{len(capacity)} satır (alt sınır 400)."
    else:
        updated = pd.to_datetime(capacity["Row Updated At"], errors="coerce", format="mixed").max()
        stale = pd.isna(updated) or updated < pd.Timestamp(day)
        freshness = f"Son güncelleme {updated:%d.%m.%Y %H:%M}." if pd.notna(updated) else "Güncelleme tarihi okunamadı."
    if stale:
        add("hata", "Kapasite verisi eksik veya eski", freshness, f"Sekme {capacity_id} / " + ("satır sayısı" if kind == "amb" else "Row Updated At"))
    absent = set(depots) - set(capacity["Depo: Depo Adı"].dropna().map(_norm))

    def missing_depots(level, title, names, fallback, origin):
        if not names:
            return
        labels = sorted(depots[n] for n in names if not depots[n].strip().upper().endswith(" SC"))
        sc = len(names) - len(labels)
        examples = ", ".join(labels[:5])
        details = " · ".join(v for v in (f"{sc} SC depo" if sc else "", examples,
                                        f"{len(labels)-5} depo daha" if len(labels) > 5 else "") if v)
        add(level, title, f"{len(names)} depo ({details}). {fallback}", origin)

    missing_depots("uyari", "Depo kapasitesi eksik", absent, "Hacim kısıtı uygulanmaz.", f"Sekme {capacity_id} / Depo: Depo Adı")
    buffer = part(snapshot, BUFFER, "Ambient Buffer" if kind == "amb" else "Cold Limit")
    missing_depots("bilgi", "Depo buffer’ı eksik", {n for n in depots if not buffer.get(n)}, "%110 varsayılan.", "Buffer Rates / Depo Adı")
    if kind != "amb":
        share = table(snapshot, SHARE)
        share["_depot"] = share["Depo Adı"].map(_norm)
        missing_depots("bilgi", "Sharing payı eksik", set(depots) - set(share["_depot"]), "Motor varsayılan paylaşımı kullanır.", "MS_Other4_Sharing / Depo Adı")
        g10 = set(d.loc[domain(d).eq("G10"), "Location name"].map(_norm))
        invalid = set()
        for first, second in (("Other+4", "MS+4"), ("Taze Et", OTHER_ETB)):
            g = share[share["_depot"].isin(g10)]
            a, b = g[first].map(ratio).astype(float), g[second].map(ratio).astype(float)
            invalid.update(g.loc[~np.isclose(a + b, 1, atol=.01000001, rtol=0), "_depot"])
        missing_depots("uyari", "G10 sharing toplamı 1 değil", invalid, "İlgili payları doğrulayın.", f"MS_Other4_Sharing / Other+4, MS+4, Taze Et, {OTHER_ETB}")
    else:
        weekday = WEEKDAYS[date.fromisoformat(day).weekday()]
        truck = part(snapshot, TRUCK, weekday)
        missing_depots("bilgi", "Günlük TIR limiti eksik", {n for n in depots if not truck.get(n)}, "Varsayılan G10 12, GB 25 palet.", f"Depo Palet Limitleri / {weekday}")
        missing_depots("bilgi", "Su palet alanı eksik", set(depots) - set(table(snapshot, WATER_SPACE)["Depo"].dropna().map(_norm)), "Su alanı kısıtı uygulanmaz.", "Su palet alanı / Depo")

    backlog_title, _ = sheets.ELLE_SEKMELER[kind]["backlog"]
    backlog = pd.read_excel(snapshot / "xlsx" / sheets.dosya_adi(backlog_title))
    backlog_names = set(backlog["Location name"].dropna().map(_norm))
    extra, negative = backlog_names - set(depots), numbers(backlog["Backlog_Palet_Sayisi"]).lt(0)
    absent = set(depots) - backlog_names if kind == "amb" else set()
    if extra or absent or negative.any():
        extra_names = ", ".join(sorted({str(n) for n in backlog["Location name"].dropna() if _norm(n) in extra})[:5])
        add("uyari", "Backlog tutarsızlığı", f"Relex’te olmayan {len(extra)} depo"
            + (f" ({extra_names})" if extra_names else "")
            + f", Backlog'da eksik {len(absent)} depo, negatif {negative.sum()} satır.", backlog_title + " / Location name, Backlog_Palet_Sayisi")
    return notes


def history_paths(center, day, kind, limit=3, include_day=False):
    import os

    archive = Path(os.environ.get("TRANSFER_HISTORY_DIR", Path(__file__).with_name("izmir_gecmis")))
    run_history = os.environ.get("TRANSFER_RUN_HISTORY_DIR")
    locations = ([archive] if center == "İzmir" else []) + ([Path(run_history)] if run_history else [])
    run_date = date.fromisoformat(day)
    results = {}
    for location in locations:
        if not location.is_dir():
            continue
        for folder in sorted(location.iterdir()):
            try:
                if "." in folder.name:
                    d, m = map(int, folder.name.split("."))
                    archived = date(run_date.year, m, d)
                    if run_date.month == 1 and m == 12:
                        archived = archived.replace(year=run_date.year - 1)
                else:
                    archived = date.fromisoformat(folder.name)
            except ValueError:
                continue
            path = folder / CATEGORIES[kind] / f"{center}.parquet"
            if (archived < run_date or (include_day and archived == run_date)) and path.is_file():
                results[archived.isoformat()] = path
    return sorted(results.items(), reverse=True)[:limit]


def parameter_checks(snapshot, kind, center, day, relex):
    from calistir import varsayilan_parametreler

    changes, notes = {}, []
    keys = relex["Location name"].map(_norm)
    names = dict(zip(keys, relex["Location name"]))
    domains = dict(zip(keys, domain(relex)))
    cold_defaults = varsayilan_parametreler("cold") if kind != "amb" else {}
    params = [(kind, BUFFER, "Ambient Buffer", "Hard_Stop_Orani", 1.10, None)] if kind == "amb" else [
        ("cold", BUFFER, "Cold Limit", "buffer_rate", 1.10, None),
        ("cold", SHARE, "Other+4", "other4_oran", None, "Other"),
        ("cold", SHARE, OTHER_ETB, "etb_oran", None, "ETB"),
    ]
    if kind == "amb":
        params.append((kind, TRUCK, None, "Tir_Limiti", None, None))
    records = {}
    for category, gid, column, old_col, default, group in params:
        for archived, path in history_paths(center, day, category):
            if path not in records:
                records[path] = pd.read_parquet(path)
            past = records[path]
            if old_col not in past:
                continue
            historical = past
            if group and "Item_group" in past:
                historical = past[past["Item_group"].eq(group)]
            column_for_day = column or WEEKDAYS[date.fromisoformat(archived).weekday()]
            values = part(snapshot, gid, column_for_day)
            past_values = historical.dropna(subset=["Location name", old_col]).drop_duplicates("Location name")
            for _, row in past_values.iterrows():
                key = _norm(row["Location name"])
                if key not in names:
                    continue
                old, explicit = ratio(row[old_col]), values.get(key)
                if gid in (BUFFER, TRUCK, SHARE) and not explicit:
                    explicit = None
                fallback = default
                if gid == TRUCK:
                    fallback = 12 if domains[key] == "G10" else 25
                elif gid == SHARE:
                    group_key = "OTHER4" if column == "Other+4" else "ETB"
                    fallback = cold_defaults[f"{domains[key]}_DEFAULT_{group_key}_ORAN"]
                current = explicit if explicit is not None else fallback
                origin = str(row.get("Tir_Limiti_Kaynagi", ""))
                from_sheet = origin.startswith("Gunluk Sheet")
                if gid == TRUCK and not from_sheet and not origin:
                    continue
                if current is None and old is None:
                    continue
                if gid == TRUCK and not from_sheet and explicit is not None:
                    status = "Yeni eklendi"
                elif explicit is None:
                    verified = (gid == TRUCK and from_sheet) or (old is not None and old != fallback)
                    status = "Varsayılana düştü" if verified else "Değişti"
                elif old is None:
                    status = "Yeni eklendi"
                else:
                    status = "Değişti"
                same = old == current or (old is not None and current is not None and np.isclose(old, current, rtol=0, atol=1e-8))
                if same and not (gid == TRUCK and from_sheet != (explicit is not None)):
                    continue
                entry = changes.setdefault((key, gid, column_for_day), dict(old=[], current=current,
                    status=status, size=abs((current or 0) - (old or 0))))
                fmt = lambda v: f"{v:g}" if v is not None else "varsayılan"
                entry["old"].append(f"{archived}: {fmt(old)}")
                if gid == BUFFER and old is not None and current < old and "context" not in entry:
                    needed = {"Location name", "hacim2", "Hacimden_Kesilen_Miktar"}
                    if needed.issubset(historical.columns):
                        relevant = historical[historical["Location name"].map(_norm).eq(key)]
                        cut = (numbers(relevant["hacim2"]) * numbers(relevant["Hacimden_Kesilen_Miktar"])).dropna()
                        if len(cut):
                            entry["context"] = f" {archived} tarihinde hacimden {cut.sum():.1f} L kısıldı."
    for (key, gid, col), entry in sorted(changes.items(), key=lambda item: -item[1]["size"]):
        new = entry["current"]
        notes.append(finding("parametre-takibi", "uyari", f"{names[key]} · {col}",
            f"{entry['status']}. {', '.join(entry['old'])} → " + (f"{new:g}" if new is not None else "varsayılan") + entry.get("context", ""),
            f"Sekme {gid} / {col} ve geçmiş parquet", score=entry["size"]))
    campaign = table(snapshot, CAMPAIGN)
    counts = " · ".join(f"{col} {ids(campaign[col]).dropna().nunique()} ürün" for col in campaign.columns)
    availability = f"{len(records)} geçmiş koşu ile karşılaştırıldı." if records else "Karşılaştırılabilir geçmiş arşivi yok."
    notes.append(finding("parametre-takibi", "bilgi", "Kampanya ve parametre geçmişi",
        f"{availability} {counts}.", f"Kampanya / {CAMPAIGN}"))
    return notes


def unit_volumes(snapshot, kind):
    if kind == "cold":
        tab = table(snapshot, 1098615637)
        tab = tab[tab["Measure Names"].str.strip().eq("Max. Product Volume m3")]
        product, value = "Product ID", "Measure Values"
    else:
        tab = table(snapshot, 1615488785)
        product, value = "marketproduct_id", "hacim2"
    measured = numbers(tab[value].str.strip().str.replace(",", ".", regex=False))
    return measured[measured.gt(0)].groupby(ids(tab[product])).max().to_dict()


def relex_evidence(row, batch, current, proposed, reason, **fields):
    return dict(depotCode=str(row["Location code"]), productCode=str(row["Product code"]),
        depot=str(row["Location name"]), product=str(row["Product name"]),
        domain=str(row["Domain Type"] or "GB"), current=float(current), proposed=float(proposed), batch=float(batch),
        unit="kg" if row["Transfer type"] == "BULK" else "adet", reason=reason, **fields)


def relex_anomalies(snapshot, kind, center, day, relex):
    d = relex.copy()
    d["Domain Type"] = domain(d)
    d["_product"] = ids(d["Product code"])
    d["_q"] = numbers(d["Effective quantity"])
    d["_batch"] = numbers(d["Order batch size"]).clip(lower=1)
    d["_fc"], d["_sales"] = numbers(d["Daily FC"]), numbers(d["14 Days Sales"])
    campaign = table(snapshot, CAMPAIGN)
    protected = pd.Series(False, index=d.index)
    for dtype in ("G10", "GB"):
        products = ids(pd.concat([campaign[f"{dtype} T"], campaign[f"{dtype} T-1"]])).dropna()
        protected |= d["Domain Type"].eq(dtype) & d["_product"].isin(products)
    protected |= (d["Custom category"].fillna("") + " " + d["Custom sub-category"].fillna("")).map(_norm).str.contains("demirbas")
    if kind == "amb":
        protected |= d["_product"].isin(ids(table(snapshot, WATER)["Product ID"]).dropna())
    d = d[d["_q"].gt(0) & ~protected].copy()
    group_cols = ["_product", "Domain Type", "Transfer type"]
    grouping = d.groupby(group_cols, dropna=False)
    median = grouping["_q"].transform("median")
    fc_median = grouping["_fc"].transform("median")
    outlier = (grouping["Location code"].transform("nunique").ge(5) &
        d["_q"].ge(4 * median) & (d["_q"] - median).ge(3 * d["_batch"]))
    demand = d["_q"].gt(d["_sales"]) | (d["_fc"].gt(0) & d["_fc"].ge(2 * d["_sales"] / 14) & d["_fc"].ge(3 * fc_median))
    candidates = d[outlier & demand]
    history = []
    for archived, path in history_paths(center, day, kind):
        past = pd.read_parquet(path)
        needed = {"Product code", "Location code", "Domain Type", "Effective quantity"}
        if needed.issubset(past.columns):
            past = past.assign(_product=ids(past["Product code"]), _q=numbers(past["Effective quantity"]),
                _day=archived, **{"Domain Type": domain(past)})
            if "Transfer type" not in past:
                past["Transfer type"] = {"amb": "AMBIENT", "cold": "COLD_FOOD", "ms": "FV"}[kind]
                if kind == "ms" and "Is_Bulk" in past:
                    past.loc[past["Is_Bulk"].eq(True), "Transfer type"] = "BULK"
            history.append(past[past["_q"].gt(0)])
    past = pd.concat(history, ignore_index=True) if history else pd.DataFrame(columns=group_cols + ["_q", "_day", "Location code"])
    past_groups = past.groupby(group_cols)["_q"].median() if not past.empty else {}
    changes, rising = [], set()
    volumes = unit_volumes(snapshot, kind) if not candidates.empty else {}
    for idx, row in candidates.iterrows():
        keys = tuple(row[c] for c in group_cols)
        historical = past_groups.get(keys)
        med = median[idx]
        if historical and med >= 3 * historical:
            rising.add((row["Product name"], row["Domain Type"]))
            continue
        current, b, sales = row["_q"], row["_batch"], row["_sales"]
        stock = numbers(pd.Series([row["End balance"], row["Open purchase orders"]]))
        proposed = max(b, round(med / b) * b)
        if pd.notna(sales) and stock.notna().all() and stock.sum() >= sales:
            proposed = 0
        if proposed >= current:
            continue
        depot_past = past[past["_product"].eq(row["_product"]) &
            ids(past["Location code"]).eq(str(row["Location code"]).strip().lower()) &
            past["Transfer type"].eq(row["Transfer type"])]
        recent = ", ".join(f"{r['_day']}: {r['_q']:g}" for _, r in depot_past.iterrows())
        fmt = lambda v: f"{v:g}" if pd.notna(v) else "yok"
        evidence = (f"Öneri {current:g}, {row['Domain Type']} medyanı {med:g} ({current/med:.1f} kat). "
                    f"14 günlük satış {fmt(sales)}, Daily FC {fmt(row['_fc'])}, stok {fmt(stock[0])}, batch {b:g}."
                    + (f" Geçmiş öneri: {recent}." if recent else ""))
        volume = volumes.get(row["_product"]) if row["Transfer type"] != "BULK" else None
        excess = (current - med) * volume if volume is not None else current - med
        if volume is not None:
            evidence += f" Medyan üzerindeki öneri {excess:.1f} L."
        changes.append(relex_evidence(row, b, current, proposed, "relex-anomali",
            median=float(med), evidence=evidence, score=float(excess), hasLiters=volume is not None))
    notes = []
    if rising:
        notes.append(finding("relex-anomali", "bilgi", "Depolar genelinde öneri artışı",
            f"{len(rising)} ürün × depo tipinde medyan geçmişin en az 3 katı. Kampanya veya sezon etkisi olabilir.",
            relex_path(snapshot, kind).name + " / Effective quantity ve geçmiş parquet"))
    return changes, notes


def iqr_outliers(snapshot, kind, relex):
    """Depots whose proposal is far above the same product's G10/GB peers (IQR rule), pulled to the median.

    Complements relex_anomalies, which also requires excess demand; same exemptions (campaign, demirbaş, water).
    """
    d = relex.copy()
    d["Domain Type"] = domain(d)
    d["_product"] = ids(d["Product code"])
    d["_q"] = numbers(d["Effective quantity"])
    d["_batch"] = numbers(d["Order batch size"])
    campaign = table(snapshot, CAMPAIGN)
    protected = pd.Series(False, index=d.index)
    for dtype in ("G10", "GB"):
        products = ids(pd.concat([campaign[f"{dtype} T"], campaign[f"{dtype} T-1"]])).dropna()
        protected |= d["Domain Type"].eq(dtype) & d["_product"].isin(products)
    protected |= (d["Custom category"].fillna("") + " " + d["Custom sub-category"].fillna("")).map(_norm).str.contains("demirbas")
    protected |= d["Product name"].fillna("").map(_norm).str.contains("beypazar")
    if kind == "amb":
        protected |= d["_product"].isin(ids(table(snapshot, WATER)["Product ID"]).dropna())
    # Compare independent depots with exactly one non-bulk proposal for the product.
    valid = d["Domain Type"].isin(["G10", "GB"]) & d["_product"].notna() & d["Location code"].notna()
    valid &= ~d.duplicated(["Location code", "Product code"], keep=False)
    valid &= d["_q"].ge(0) & ~d["Transfer type"].astype(str).str.strip().str.upper().eq("BULK")
    d = d[valid]
    groups = d.groupby(["_product", "Domain Type"])["_q"]
    median, mean, count = groups.transform("median"), groups.transform("mean"), groups.transform("count")
    q1, q3 = groups.transform("quantile", q=.25), groups.transform("quantile", q=.75)
    spread = pd.concat([q3 - q1, .25 * median], axis=1).max(axis=1).clip(lower=1)
    limit = q3 + 1.5 * spread
    hits = d[count.ge(8) & d["_q"].gt(limit) & d["_q"].gt(d["_batch"]) & d["_batch"].gt(0) & ~protected.reindex(d.index)]
    volumes = unit_volumes(snapshot, kind) if not hits.empty else {}
    changes = []
    for idx, row in hits.iterrows():
        current, b, med = row["_q"], row["_batch"], median[idx]
        proposed = max(b, (med // b) * b)
        if proposed >= current:
            continue
        volume = volumes.get(row["_product"])
        excess = (current - med) * volume if volume is not None else current - med
        evidence = (f"Öneri {current:g}, {row['Domain Type']} medyanı {med:g}, ortalama {mean[idx]:.1f}; "
                    f"aykırılık üst sınırı {limit[idx]:.1f} ({count[idx]} depo). Batch {b:g}."
                    + (f" Medyan üzerindeki öneri {excess:.1f} L." if volume is not None else ""))
        changes.append(relex_evidence(row, b, current, proposed, "relex-anomali", median=float(med),
                                      evidence=evidence, score=float(excess), hasLiters=volume is not None))
    return changes


def volume_load(snapshot, kind, draft, relex):
    p = draft.copy()
    if kind == "amb":
        p = p[~p["Is_Water"].eq(True) & p["Cut_Priority"].lt(100)].copy()
        p["_allowed"] = p["Kalan_Net_Hacim_Litre"] + p["Avg. ambient_dolap_hacim"] * (p["Hard_Stop_Orani"] - 1)
        p["_group"] = "Ambient"
    elif kind == "cold":
        p = p[p["Doluluk_Tablosunda_Var_Mi"].eq(True) & p["Cut_Priority"].lt(100)].copy()
        p["_allowed"], p["_group"] = p["Kullanilabilir_Limit_Litre"], p["Item_group"]
    else:
        p = p[p["Doluluk_Tablosunda_Var_Mi"].eq(True) & ~p["Is_Bulk"].eq(True)].copy()
        if "Cut_Priority" in p:
            p = p[p["Cut_Priority"].lt(100)].copy()
        p["_allowed"], p["_group"] = p["Allowed_Space"], p["Cabinet_Type"]
    p["_liters"] = p["Effective_Units"] * p["Vol_Per_Unit"] if kind == "ms" else p["Satir_Onerilen_Hacim"]
    r = relex.copy()
    r["Domain Type"] = domain(r)
    columns = ["Location code", "Product code"]
    for c in columns:
        r[c], p[c] = ids(r[c]), ids(p[c])
    original = r.set_index(columns)
    campaign = table(snapshot, CAMPAIGN)
    protected = {dtype: set(ids(pd.concat([campaign[f"{dtype} T"], campaign[f"{dtype} T-1"]])).dropna())
                 for dtype in ("G10", "GB")}
    changes = []
    for (_, group), rows in p.groupby(["Location code", "_group"]):
        if not rows["_allowed"].notna().any():
            continue
        overload = rows["_liters"].sum() - rows["_allowed"].dropna().iloc[0]
        if overload <= 0:
            continue
        candidates = rows[rows["_liters"].ge(max(overload * .25, 20 if kind == "amb" else 10))]
        accepted = 0
        for _, draft_row in candidates.sort_values("_liters", ascending=False, kind="stable").iterrows():
            key = tuple(draft_row[c] for c in columns)
            if key not in original.index or draft_row.get("Trim_Exempt", False) == True:
                continue
            row = original.loc[key].copy()
            row["Location code"], row["Product code"] = key
            designation = _norm(f"{row['Custom category']} {row['Custom sub-category']}")
            if row["Product code"] in protected[row["Domain Type"]] or "demirbas" in designation:
                continue
            vals = numbers(row[["Effective quantity", "Order batch size", "Daily FC", "End balance",
                               "Open purchase orders", "14 Days Sales"]])
            q, b, fc, stock, orders, sales = vals
            if pd.isna(fc) or fc <= 0 or pd.isna(stock) or pd.isna(orders) or q <= 0:
                continue
            cover = (stock + orders + q) / fc
            if not (cover >= 10 or (pd.notna(sales) and q > sales)):
                continue
            new = max(0, np.ceil((7 * fc - stock - orders) / b) * b)
            if new >= q:
                continue
            liters = draft_row["_liters"]
            evidence = (f"{group} aşımı {overload:.1f} L. Ürün {liters:.1f} L (%{100*liters/overload:.0f}). "
                        f"Öneri {q:g}, cover {cover:.1f} gün, 14 günlük satış {sales if pd.notna(sales) else 'yok'}, batch {b:g}. "
                        f"Tahmini azalan hacim {liters*(q-new)/q:.1f} L.")
            changes.append(relex_evidence(row, b, q, new, "hacim-yuku", evidence=evidence, score=float(liters), hasLiters=True))
            accepted += 1
            if accepted == 2:
                break
    return changes


def grouped_changes(changes, phase, source):
    groups = {}
    for item in changes:
        key = (item["productCode"].strip().lower(), item["domain"], item["unit"])
        groups.setdefault(key, []).append(item)
    return [finding(phase, "uyari", f"{rows[0]['product']} · {rows[0]['domain']}",
                    f"{len(rows)} depo için miktar önerisi.", source, edits=rows,
                    score=sum(row["score"] for row in rows), hasLiters=rows[0]["hasLiters"]) for rows in groups.values()]
