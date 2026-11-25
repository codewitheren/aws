"""Allow one typed scenario edit, in a disposable copy of the input snapshot."""
from datetime import date
from math import isfinite

from sys import float_info

import pandas as pd
from openpyxl import load_workbook

import calistir
from analytics import select
from preflight import BUFFER, CAMPAIGN, OTHER_ETB, SHARE, TRUCK, WEEKDAYS, relex_path
from surucu import _norm

SHEETS = {
    "buffer": (BUFFER, ("Ambient Buffer", "Cold Limit")),
    "sharing": (SHARE, ("Other+4", "MS+4", "MS+8+12", "Taze Et", OTHER_ETB)),
    "tir": (TRUCK, WEEKDAYS),
}


def finite(value):
    if type(value) not in (int, float) or abs(value) > float_info.max or not isfinite(value):
        raise ValueError("Sonlu bir sayısal değer gerekli.")
    return value


def apply_changes(snapshot, kind, changes):
    path = relex_path(snapshot, kind)
    with path.open("rb") as stream:
        book = load_workbook(stream)
    try:
        sheet = book.worksheets[0]
        header = {cell.value: cell.column for cell in sheet[1]}
        code, product, quantity = [header[c] for c in ("Location code", "Product code", "Effective quantity")]
        rows = {}
        for cells in sheet.iter_rows(min_row=2):
            key = tuple(str(cells[c - 1].value).strip().lower() for c in (code, product))
            rows.setdefault(key, []).append(cells[quantity - 1])
        for change in changes:
            key = tuple(change[c].strip().lower() for c in ("depotCode", "productCode"))
            candidates = rows.get(key, [])
            if len(candidates) != 1 or float(candidates[0].value) != change["current"]:
                raise ValueError("Revize satırı veya orijinal öneri girdiyle eşleşmedi.")
            candidates[0].value = change["value"]
        book.save(path)
    finally:
        book.close()


def edit_scenario(snapshot, kind, day, change):
    allowed = {"type", "value", "field", "depot", "product"}
    if not isinstance(change, dict) or change.keys() - allowed:
        raise ValueError("Geçerli tek bir senaryo değişikliği gerekli.")
    category, name, depot, product = (change.get(k, "") for k in ("type", "field", "depot", "product"))
    if any(not isinstance(field, str) or len(field) > 150 for field in (category, name, depot, product)):
        raise ValueError("Geçersiz senaryo alanı.")
    value = change.get("value")
    if category == "parametre":
        params = calistir.varsayilan_parametreler(kind)
        previous = params.get(name)
        if type(previous) not in (bool, int, float, list):
            raise ValueError("Bu motor parametresi senaryoda değiştirilemiyor.")
        if type(previous) is list:
            if not isinstance(value, list) or len(value) > 1000 or any(
                not isinstance(item, str) or len(item) > 150 for item in value
            ):
                raise ValueError("Bu parametre metin değerlerinden oluşan bir liste bekliyor.")
        elif type(previous) is bool:
            if type(value) is not bool:
                raise ValueError("Bu parametre true/false bekliyor.")
        else:
            finite(value)
            if type(previous) is int and not isinstance(value, int):
                raise ValueError("Bu parametre bir tam sayı bekliyor.")
        return dict(type=category, field=name, before=previous, after=value), {name: value}, {}
    relex = pd.read_excel(relex_path(snapshot, kind), dtype={"Location code": str, "Product code": str})
    scope = {k: v for k, v in (("depot", depot), ("product", product)) if v}
    chosen, matches = select(relex, **{**{"depot": "", "product": "", "depot_type": ""}, **scope})
    if chosen is None:
        raise ValueError(f"Depo veya ürün eşleşmesi belirsiz: {matches}")
    if category == "relex":
        if not (depot and product) or len(chosen) != 1:
            raise ValueError("Relex senaryosu tek bir depo × ürün gerektirir.")
        row = chosen.iloc[0]
        b = float(row["Order batch size"])
        previous = float(row["Effective quantity"])
        requested = finite(value)
        if requested < 0:
            raise ValueError("Relex miktarı negatif olamaz.")
        unit = "kg" if kind == "ms" and row["Transfer type"] == "BULK" else "adet"
        value = requested if unit == "kg" else b * round(requested / b)
        apply_changes(snapshot, kind, [dict(depotCode=row["Location code"], productCode=row["Product code"],
            value=value, current=previous)])
        return dict(type=category, before=previous, after=value, requested=requested, batch=b, unit=unit, **matches), {}, scope
    if category == "kampanya":
        if kind == "ms":
            raise ValueError("MS motoru kampanya sekmesini kullanmıyor.")
        if not product or depot or name not in ("G10 T", "G10 T-1", "GB T", "GB T-1") or type(value) is not bool:
            raise ValueError("Kampanya için ürün, G10/GB × T/T-1 kolonu ve ekleme (true) / çıkarma (false) gerekli.")
        path = snapshot / "sheets" / str(CAMPAIGN)
        tab = pd.read_csv(path, dtype=str, keep_default_na=False)
        code = matches["product"]["code"]
        matches_code = tab[name].str.strip().str.lower().eq(code.strip().lower())
        previous = bool(matches_code.any())
        if value and not previous:
            blank = tab.index[tab[name].eq("")]
            tab.loc[blank[0] if len(blank) else len(tab), name] = code
        if not value:
            tab.loc[matches_code, name] = ""
        tab.to_csv(path, index=False)
        return dict(type=category, field=name, before=previous, after=value, **matches), {}, scope
    if category not in SHEETS or not depot or product:
        raise ValueError("Buffer, sharing ve TIR senaryoları tek bir depo gerektirir.")
    if (category == "tir" and kind != "amb") or (category == "sharing" and kind == "amb"):
        raise ValueError("Bu sekme seçili kategorinin motorunda kullanılmıyor.")
    if category == "buffer":
        name = "Ambient Buffer" if kind == "amb" else "Cold Limit"
        if not 0 < finite(value) or not isfinite(value * 100):
            raise ValueError("Buffer için pozitif oran ölçeği kullanın (ör. %120 için 1.20).")
        written = f"{value * 100:g}%"
    elif category == "tir":
        name = WEEKDAYS[date.fromisoformat(day).weekday()]
        if type(value) is not int or value < 0:
            raise ValueError("TIR limiti sıfır veya pozitif tam sayı olmalı.")
        written = str(value)
    else:
        if not 0 <= finite(value) <= 1:
            raise ValueError("Sharing payı 0–1 aralığında olmalı.")
        written = str(value)
    gid, columns = SHEETS[category]
    if name not in columns:
        raise ValueError("Bu senaryo için geçerli sekme kolonu gerekli.")
    path = snapshot / "sheets" / str(gid)
    tab = pd.read_csv(path, dtype=str, keep_default_na=False)
    headers = {col.strip(): col for col in tab}
    depot_rows = tab.index[tab[headers["Depo Adı"]].map(_norm).eq(_norm(matches["depot"]))]
    if len(depot_rows) > 1:
        raise ValueError("Sekmede birden fazla depo satırı eşleşti.")
    row = depot_rows[0] if len(depot_rows) else len(tab)
    previous = tab.loc[row, headers[name]] if len(depot_rows) else None
    tab.loc[row, headers["Depo Adı"]] = matches["depot"]
    tab.loc[row, headers[name]] = written
    paired = {}
    if category == "sharing" and chosen["Domain Type"].fillna("GB").eq("G10").any():
        complements = {"Other+4": "MS+4", "MS+4": "Other+4", "Taze Et": OTHER_ETB, OTHER_ETB: "Taze Et"}
        if name in complements:
            partner = complements[name]
            tab.loc[row, headers[partner]] = f"{1-value:.8g}"
            paired[partner] = round(1 - value, 8)
    tab.to_csv(path, index=False)
    return dict(type=category, field=name, before=previous, after=written,
        newRow=not len(depot_rows), complements=paired, **matches), {}, scope
