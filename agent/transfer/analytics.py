"""Metrics from the motor's row-level parquet, with category-specific units."""
import pandas as pd

from preflight import CATEGORIES, domain, history_paths, ids, numbers
from surucu import _amb_neden, _cold_neden, _ms_neden, _norm

COLUMNS = {
    "amb": ("Orijinal_Miktar", "Final_Miktar", "Kesinti_Nedeni", "hacim2", "Final_Hacim_Litre"),
    "cold": ("Orijinal_Miktar", "Final_Miktar", "Kesinti_Nedeni", "hacim2", "Final_Hacim_Litre"),
    "ms": ("Effective_Units", "Final_Quantity", "Trim_Reason", "Vol_Per_Unit", "Final_Item_Volume"),
}
CONTEXT = {
    "amb": ["Orijinal_Teslimat_Sonrasi_Doluluk (%)", "Gelecek_Teslimat_Sonrasi_Doluluk (%)", "Hard_Stop_Orani",
            "Tir_Limiti", "Tir_Limiti_Kaynagi", "Etkili_Backlog_Palet", "Depo_Orijinal_Palet_Toplami", "Depo_Final_Palet_Toplami"],
    "cold": ["Kapasite_Litre", "Uygulanan_Buffer", "Uygulanan_Oran", "Backlog_Palet_Sayisi"],
    "ms": ["Son_Doluluk_Pct", "Allowed_Space", "Backlog"],
}


def numeric(frame, column):
    return numbers(frame[column]) if column in frame else pd.Series(float("nan"), index=frame.index)


def clean(value):
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def pct(a, b):
    return round(100 * a / b, 2) if b else None


def reason_bucket(kind, raw, cut):
    if kind == "amb":
        label = _amb_neden(raw)
        if label.startswith("TIR"):
            return "TIR / palet limiti"
        if label.startswith("Merkez"):
            return "Merkez limiti"
    elif kind == "cold":
        label = _cold_neden(raw)
    else:
        label = _ms_neden(raw, cut)
        if label in ("Backlog engeli", "Kara liste"):
            return "Backlog blokajı"
        if label == "Dolapta yer yok":
            return "Dolap hacmi"
        if label.startswith("Dökme"):
            return "Dökme / yuvarlama"
    if label.startswith("Merkez"):
        return "Merkez limiti"
    return label or "Diğer"


def prepared(kind, frame):
    original, final, reason, volume, final_volume = COLUMNS[kind]
    data = frame.copy()
    data["_proposed"] = numeric(data, original).fillna(0).clip(lower=0)
    data["_final"] = numeric(data, final).fillna(0)
    data["_cut"] = (data["_proposed"] - data["_final"]).clip(lower=0).where(data["_proposed"].gt(0), 0)
    data["_liters"] = numeric(data, volume) * data["_cut"]
    data["_proposalL"] = (numeric(data, volume) * data["_proposed"] if kind == "ms"
                          else numeric(data, "Satir_Onerilen_Hacim"))
    data["_finalL"] = numeric(data, final_volume)
    data["_unit"] = "adet"
    if kind == "ms" and "Is_Bulk" in data:
        data.loc[data["Is_Bulk"].eq(True), "_unit"] = "kg"
    raw = data[reason].fillna("").astype(str)
    data["_reason"] = [reason_bucket(kind, why, cut) for why, cut in zip(raw, data["_cut"])]
    return data


def row_counts(data):
    proposed, final = data["_proposed"], data["_final"]
    n, created = int(proposed.gt(0).sum()), int(final.gt(0).sum())
    return dict(proposedRows=n, createdRows=created, deletedRows=int((proposed.gt(0) & final.eq(0)).sum()),
        reducedRows=int((final.gt(0) & final.lt(proposed)).sum()), cpPct=pct(created, n))


def sum_or_none(series):
    return round(float(series.sum()), 3) if series.notna().any() else None


def unit_metrics(data):
    proposed, final, cut = (float(data[c].sum()) for c in ("_proposed", "_final", "_cut"))
    trimmed = data[data["_cut"].gt(0)]
    why = trimmed.groupby("_reason")["_cut"].sum().sort_values(ascending=False)
    result = dict(**row_counts(data), proposed=round(proposed, 3), final=round(final, 3), cut=round(cut, 3),
        cutPct=pct(cut, proposed), cutLiters=sum_or_none(trimmed["_liters"]) if not trimmed.empty else 0,
        proposedLiters=sum_or_none(data["_proposalL"]), finalLiters=sum_or_none(data["_finalL"]),
        reasons=[dict(reason=k, cut=round(float(v), 3), sharePct=pct(v, cut)) for k, v in why.items()])
    for key, column in [("backlogCutWithinTruck", "Backlog_Kesilen_Miktar"), ("aClassCut", "ABC class")]:
        if column in data:
            value = (float(numeric(trimmed, column).sum()) if key == "backlogCutWithinTruck" else
                     float(trimmed.loc[trimmed[column].eq("A"), "_cut"].sum()))
            result[key] = round(value, 3)
    return result


def metrics(kind, frame):
    data = prepared(kind, frame)
    return dict(**row_counts(data), quantities={unit: unit_metrics(rows) for unit, rows in data.groupby("_unit")},
                columns=list(COLUMNS[kind]))


def select(frame, depot, product, depot_type):
    scoped = frame
    matches = {}
    if depot:
        depots = scoped["Location name"].dropna().astype(str).unique()
        name = _norm(depot)
        options = [n for n in depots if name == _norm(n)] or [n for n in depots if name and name in _norm(n)]
        if len(options) != 1:
            return None, {"depo": sorted(options)[:10]}
        scoped = scoped[scoped["Location name"].eq(options[0])]
        matches["depot"] = options[0]
    if product:
        products = frame[["Product code", "Product name"]].dropna().drop_duplicates("Product code")
        query = _norm(product)
        candidates = products[ids(products["Product code"]).eq(product.strip().lower())]
        if candidates.empty:
            normalized = products["Product name"].map(_norm)
            exact = normalized.eq(query)
            candidates = products[exact] if exact.any() else products[normalized.str.contains(query, regex=False) & bool(query)]
        if len(candidates) != 1:
            return None, {"urun": candidates.head(5).to_dict("records")}
        code, name = candidates.iloc[0]
        scoped = scoped[ids(scoped["Product code"]).eq(str(code).strip().lower())]
        matches["product"] = {"code": str(code), "name": name}
    if depot_type:
        if depot_type not in ("G10", "GB"):
            return None, {"depoTipi": ["G10", "GB"]}
        scoped = scoped[domain(scoped).eq(depot_type)]
    return scoped, matches


def depot_context(kind, data):
    rows = []
    group = {"amb": None, "cold": "Item_group", "ms": "Cabinet_Type"}[kind]
    groups = data.groupby(group) if group and group in data else [(None, data)]
    for key, part in groups:
        row = {"group": key}
        wanted = list(CONTEXT[kind])
        if kind == "cold" and key:
            wanted.extend(f"{key}_{suffix} (%)" for suffix in (
                "Kesintisiz_Gelecek_Doluluk", "Gelecek_Teslimat_Sonrasi_Doluluk"))
        for column in wanted:
            if column in part:
                values = part[column].dropna().unique()
                if len(values) == 1:
                    row[column] = clean(values[0])
        rows.append(row)
    return rows


def query(kind, frame, depot="", product="", depot_type="", why=False):
    scoped, matches = select(frame, depot, product, depot_type)
    if scoped is None:
        return {"eslesmeler": matches}
    data = prepared(kind, scoped)
    result = dict(scope=matches, **row_counts(data),
        quantities={u: unit_metrics(p) for u, p in data.groupby("_unit")}, columns=list(COLUMNS[kind]))
    if product and not data.empty:
        result["domainGroups"] = {key: {u: unit_metrics(p) for u, p in chunk.groupby("_unit")}
                                  for key, chunk in data.groupby(domain(data))}
    if depot and not data.empty:
        result["capacity"] = depot_context(kind, data)
    if why:
        cut = data[data["_cut"].gt(0)].copy()
        cut["Domain Type"] = domain(cut)
        columns = ["Location name", "Product name", "Domain Type", "ABC class", "Cut_Priority",
                   "Cover_Day_Calc" if kind == "ms" else "Calculated Cover Day",
                   "_proposed", "_final", "_cut", "_reason", COLUMNS[kind][2]]
        result["topCuts"] = {unit: part.sort_values("_cut", ascending=False).head(5)[
            [c for c in columns if c in part]].astype(object).where(lambda d: d.notna(), None).to_dict("records")
            for unit, part in cut.groupby("_unit")}
        if "Cut_Priority" in cut:
            result["protectedCuts"] = {unit: p.groupby("_reason")["_cut"].sum().to_dict()
                for unit, p in cut[cut["Cut_Priority"].ge(100)].groupby("_unit")}
    return result


def history(kind, center, day, current, depot="", depot_type="", official=()):
    current_data = query(kind, current, depot, depot_type=depot_type, why=True)
    if "eslesmeler" in current_data:
        return current_data
    sources = {when: (path, "arşiv") for when, path in history_paths(center, day, kind)}
    sources.update({when: (frame, "resmi") for when, frame in official})
    paths = sorted(sources.items(), reverse=True)[:3]
    days, past_frames = [], []
    for when, (source, origin) in paths:
        past = pd.read_parquet(source) if origin == "arşiv" else source
        past_frames.append(past)
        past_result = query(kind, past, depot, depot_type=depot_type, why=True)
        if "eslesmeler" not in past_result:
            days.append(dict(date=when, source=origin, **past_result))
    deviations = []
    if days and not depot:
        for key, threshold, relative in (("cpPct", 5, False), ("proposedRows", .30, True),
                                        ("proposedLiters", .30, True), ("cutPct", 5, False)):
            units = current_data["quantities"] if key in ("proposedLiters", "cutPct") else [None]
            for unit in units:
                def metric(record):
                    return (record["quantities"].get(unit, {}).get(key) if unit else record.get(key))
                now, past = metric(current_data), [metric(row) for row in days]
                past = [v for v in past if v is not None]
                if now is None or not past:
                    continue
                mean = sum(past) / len(past)
                off = abs(now - mean)
                if (now < min(past) or now > max(past)) and off >= (threshold * mean if relative else threshold):
                    deviations.append(dict(metric=key, unit=unit, today=now, minimum=min(past), maximum=max(past), average=mean))
    depot_changes = []
    if past_frames:
        def depot_stats(frame):
            scoped, _ = select(frame, depot, "", depot_type)
            if scoped is None:
                return {}
            rows = prepared(kind, scoped)
            return {(_norm(name), unit): (name, unit_metrics(part), part) for (name, unit), part
                in rows.groupby(["Location name", "_unit"])}
        historical = [depot_stats(frame) for frame in past_frames]
        for key, (name, stats, group) in depot_stats(current).items():
            old = [previous[key][1] for previous in historical if key in previous]
            rates = [r["cutPct"] for r in old if r["cutPct"] is not None]
            if not rates or stats["cutPct"] is None:
                continue
            mean = sum(rates) / len(rates)
            old_reasons = [r["reasons"][0]["reason"] if r["reasons"] else None for r in old]
            new_reason = stats["reasons"][0]["reason"] if stats["reasons"] else None
            chronic = len(old_reasons) == 3 and bool(old_reasons[0]) and len(set(old_reasons)) == 1
            # Pallet delta is meaningful for Ambient; the volume threshold works across categories.
            pallet_delta = 0
            if kind == "amb":
                pairs = group[["Depo_Orijinal_Palet_Toplami", "Depo_Final_Palet_Toplami"]].dropna().drop_duplicates() if {
                    "Depo_Orijinal_Palet_Toplami", "Depo_Final_Palet_Toplami"}.issubset(group.columns) else pd.DataFrame()
                if len(pairs) == 1:
                    pallet_delta = float(pairs.iloc[0, 0] - pairs.iloc[0, 1])
            unusual = stats["cutPct"] - mean >= 30 and ((stats["cutLiters"] or 0) >= 50 or pallet_delta >= 1)
            if chronic or unusual or (depot and old_reasons[0] != new_reason):
                depot_changes.append(dict(depot=name, unit=key[1], cut=stats["cut"], cutLiters=stats["cutLiters"],
                    cutPct=stats["cutPct"], averageCutPct=round(mean, 2), todayReason=new_reason,
                    latestReason=old_reasons[0], unusual=unusual, chronicReason=old_reasons[0] if chronic else None))
    # Quantities are ranked within their own units.
    depot_changes.sort(key=lambda d: (d["unit"], -d["cut"]))
    return dict(category=CATEGORIES[kind], current=current_data, historical=days, archiveDays=len(paths),
        source="İzmir.parquet / koşu gününden önceki en fazla 3 gün", deviations=deviations, depots=depot_changes[:10])


def compare_scenario(kind, before, after, scope):
    key = ["Location code", "Product code"]
    _, final, reason, _, _ = COLUMNS[kind]
    def normalized(frame):
        return frame.assign(**{c: ids(frame[c]) for c in key}).set_index(key)
    left, right = normalized(before), normalized(after)
    changed = ~(left[final].eq(right[final]) & left[reason].fillna("").eq(right[reason].fillna(""))) if (
        left.index.is_unique and right.index.is_unique and left.index.equals(right.index)) else None
    if changed is None and left.index.is_unique and right.index.is_unique:
        ix = left.index.union(right.index)
        changed = ~(left[final].reindex(ix).fillna(0).eq(right[final].reindex(ix).fillna(0)) &
            left[reason].reindex(ix).fillna("").eq(right[reason].reindex(ix).fillna("")))
    names = list(right["Location name"].reindex(changed[changed].index).dropna().unique()) if changed is not None else []
    return dict(center={"before": metrics(kind, before), "after": metrics(kind, after)},
        target={"before": query(kind, before, **scope, why=True), "after": query(kind, after, **scope, why=True)} if scope else None,
        affectedDepots=sorted(names)[:10], affectedDepotCount=len(names))
