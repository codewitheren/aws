"""Local operator workflow for reviewing and activating changes to a transfer motor."""
import argparse
import ast
from collections import Counter
from datetime import datetime
from difflib import unified_diff
from fcntl import LOCK_EX, flock
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from analytics import COLUMNS, metrics
from preflight import CATEGORIES, ids
from surucu import URUNLER, _ilk_atamalar

MOTORS = Path(__file__).resolve().with_name("motorlar")
FILES = {"amb": "Ambient_Su.py", "cold": "Cold.py", "ms": "MS.py"}
LOG = "DEGISIKLIK_KAYDI.md"
KEY = ["Location code", "Product code"]


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def atomic_copy(source, target):
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temp = Path(stream.name)
    try:
        shutil.copy2(source, temp)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def execute(kind, day, center, snapshot, output, motor_dir):
    command = [sys.executable, str(Path(__file__).with_name("calistir.py")), "ambient" if kind == "amb" else kind, "--tarih", day,
               "--cikti", str(output), "--kaynak", "yerel:" + str(snapshot)]
    proc = subprocess.run(command, text=True, capture_output=True, timeout=900,
                          env={**os.environ, "SEVK_MOTOR_DIR": str(motor_dir)})
    category = "ambient" if kind == "amb" else kind
    path = output / day / category
    log = path / "sonuc.json"
    if proc.returncode or not log.is_file():
        raise ValueError(f"{kind} motoru hata verdi. {proc.stderr[-1000:]}")
    report = json.loads(log.read_text())
    result = report["calistir"]
    if not (result["ok"] and result["allpl_ok"] and result["merkez"] == center):
        raise ValueError(f"{kind} motoru veya merkez doğrulaması başarısız. {result.get('hata')}")
    return pd.read_parquet(result["parquet"]), report


def indexed(data):
    return data.assign(**{c: ids(data[c]) for c in KEY}).set_index(KEY).sort_index()


def compare(kind, live, candidate, report, expected_depots):
    original, final, reason, *_ = COLUMNS[kind]
    missing = sorted(set(live) - set(candidate))
    a, b = indexed(live), indexed(candidate)
    if missing or not a.index.is_unique or not b.index.is_unique or not a.index.equals(b.index):
        raise ValueError(f"{kind}: kolon veya depo × ürün sözleşmesi bozuldu. Eksik kolonlar: {missing}")
    if b[final].isna().any() or b[final].lt(0).any():
        raise ValueError(f"{kind}: boş veya negatif final miktarı bulundu.")
    excess = b[final].gt(b[original] + 1e-8)
    if kind == "ms":
        excess &= ~(b["Is_Bulk"].eq(True) | b["Pick-to-zero"].astype(str).str.lower().isin(["true", "1", "1.0"]))
    if excess.any():
        raise ValueError(f"{kind}: öneriyi aşan geçersiz final miktarı bulundu.")

    def outside_batch(data):
        batch = pd.to_numeric(data["Order batch size"], errors="coerce")
        q = data[final] / batch.where(batch.gt(0))
        mask = data[final].gt(0) & ~np.isclose(q, q.round(), atol=1e-8, rtol=0)
        return int((mask & ~data["Is_Bulk"].eq(True)).sum() if kind == "ms" else mask.sum())

    if outside_batch(b) > outside_batch(a):
        raise ValueError(f"{kind}: sipariş katı dışında kalan final sayısı arttı.")
    if "Cut_Priority" in b:
        def fixture_cut(data):
            return data["Cut_Priority"].eq(101) & data[final].lt(data[original]) & ~data["Sayim_Kisiti"].eq(True)
        if (fixture_cut(b) & ~fixture_cut(a)).any():
            raise ValueError(f"{kind}: sayım dışında yeni demirbaş kesimi bulundu.")
    limit = next((item["limit"] for item in report["ozet"]["merkez"] if item["birim"] == "satır"), None)
    if limit is None or int(b[final].gt(0).sum()) > limit:
        raise ValueError(f"{kind}: merkez satır limiti aşılmış veya okunamadı.")
    changed = ~(a[final].eq(b[final]) & a[original].eq(b[original]) & a[reason].fillna("").eq(b[reason].fillna("")))
    changes = b.loc[changed, ["Location name", "Product name", original, final, reason]].copy()
    changes["önce_öneri"], changes["önce_final"], changes["önce_neden"] = a.loc[changed, [original, final, reason]].to_numpy().T
    if expected_depots and not set(changes["Location name"]).issubset(expected_depots):
        raise ValueError(f"{kind}: beklenmeyen depolar: {sorted(set(changes['Location name']) - expected_depots)}")
    return changes, dict(
        before=metrics(kind, live), after=metrics(kind, candidate), changed=int(changed.sum()),
        depots=changes["Location name"].value_counts().head(10).to_dict(),
        transitions=Counter(f"{a.at[i, reason]} → {b.at[i, reason]}" for i in changes.index),
        addedColumns=sorted(set(candidate) - set(live)), batchOutside=[outside_batch(a), outside_batch(b)], rowLimit=limit)


def prepare(args):
    directory = Path(args.cikti).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    candidate = directory / "motorlar"
    shutil.copytree(MOTORS, candidate, ignore=shutil.ignore_patterns("_yedek", "__pycache__", LOG))
    snapshot = directory / "girdi"
    shutil.copytree(Path(args.girdi).resolve(), snapshot)
    edits = json.loads(Path(args.yamalar).read_text())
    if not isinstance(edits, list) or not edits:
        raise ValueError("En az bir aday değişiklik gerekli.")
    changed_kinds = sorted({edit["kategori"] for edit in edits})
    for edit in edits:
        path = candidate / FILES[edit["kategori"]]
        before, after = edit["once"], edit["sonra"]
        original = path.read_text()
        if not before or before == after or original.count(before) != 1:
            raise ValueError(f"{path.name}: benzersiz tek bir önceki kod parçası gerekli.")
        path.write_text(original.replace(before, after, 1))

    comparison = {}
    for kind in changed_kinds:
        file = FILES[kind]
        source = (candidate / file).read_text()
        tree = ast.parse(source, filename=file)
        compile(tree, file, "exec")
        assignments = _ilk_atamalar(tree)
        old_assignments = _ilk_atamalar(ast.parse((MOTORS / file).read_text()))
        for name in URUNLER[kind]["paramlar"]:
            current = assignments.get(name)
            previous = old_assignments.get(name)
            if not current or (current.lineno != current.end_lineno and
                               (previous is None or ast.dump(current) != ast.dump(previous))):
                raise ValueError(f"{file}: {name} üst düzey tek satır atama olarak kalmalı.")
        live, live_report = execute(kind, args.tarih, args.merkez, snapshot, directory / "canli", MOTORS)
        trial, trial_report = execute(kind, args.tarih, args.merkez, snapshot, directory / "aday", candidate)
        changes, result = compare(kind, live, trial, trial_report, set(args.beklenen_depo))
        changes.to_csv(directory / f"degisen_satirlar_{kind}.csv", encoding="utf-8-sig")
        for label, report in (("before", live_report), ("after", trial_report)):
            result[label]["seconds"] = report["calistir"]["sure_sn"]["motor"]
        comparison[kind] = result
    diffs = "".join(line for kind in changed_kinds for line in unified_diff(
        (MOTORS / FILES[kind]).read_text().splitlines(keepends=True),
        (candidate / FILES[kind]).read_text().splitlines(keepends=True), FILES[kind], FILES[kind] + " (aday)"))
    (directory / "kod.diff").write_text(diffs)
    lines = ["# Aday motor karşılaştırması", "", args.kural]
    for kind, result in comparison.items():
        lines.extend(["", f"## {CATEGORIES[kind]}", "",
            f"{result['changed']} değişen satır. Merkez satır limiti {result['rowLimit']:g}.",
            "", "| Ölçü | Birim | Canlı | Aday |", "|---|---|---:|---:|"])
        for field in ("proposedRows", "createdRows", "cpPct", "seconds"):
            lines.append(f"| {field} | | {result['before'][field]} | {result['after'][field]} |")
        for unit, values in result["after"]["quantities"].items():
            for field in ("proposed", "final", "cut", "cutPct"):
                lines.append(f"| {field} | {unit} | {result['before']['quantities'].get(unit, {}).get(field)} | {values[field]} |")
        lines.extend(["", "Etkilenen depolar ve değişen satır sayıları", "",
            *[f"- {k} · {v}" for k, v in result["depots"].items()], "", "Neden geçişleri", "",
            *[f"- {k} · {v}" for k, v in result["transitions"].items()],
            "", f"Kolonlar, depo × ürün anahtarları, final sınırları ve sipariş katları doğrulandı. Eklenen kolonlar: {result['addedColumns']}."])
    (directory / "rapor.md").write_text("\n".join(lines) + "\n")
    meta = dict(center=args.merkez, date=args.tarih, rule=args.kural, comparisons=comparison,
        hashes={filename: digest(MOTORS / filename) for filename in FILES.values()},
        candidates={filename: digest(candidate / filename) for filename in FILES.values()},
        inputs={p.relative_to(snapshot).as_posix(): digest(p) for p in snapshot.rglob("*") if p.is_file()},
        report=digest(directory / "rapor.md"), diff=digest(directory / "kod.diff"), kinds=changed_kinds)
    marker = directory / "onay.json"
    marker.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"Rapor {directory / 'rapor.md'}\nKod farkı {directory / 'kod.diff'}\nAday onay kodu {digest(marker)}")


def log_change(text):
    with (MOTORS / LOG).open("a", encoding="utf-8") as stream:
        stream.write(text + "\n")


def activate(args):
    directory = Path(args.aday).resolve()
    marker = directory / "onay.json"
    if digest(marker) != args.onay:
        raise ValueError("Aday onay kodu eşleşmiyor.")
    meta = json.loads(marker.read_text())
    snapshot = directory / "girdi"
    input_hashes = {p.relative_to(snapshot).as_posix(): digest(p) for p in snapshot.rglob("*") if p.is_file()}
    if (digest(directory / "rapor.md") != meta["report"] or digest(directory / "kod.diff") != meta["diff"]
        or input_hashes != meta["inputs"]
        or any(digest(MOTORS / name) != value for name, value in meta["hashes"].items())
        or any(digest(directory / "motorlar" / name) != value for name, value in meta["candidates"].items())):
        raise ValueError("Canlı motor, aday, rapor veya girdi karşılaştırmadan beri değişmiş.")
    backup = MOTORS / "_yedek" / (datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d_%H%M%S") + "_" + directory.name)
    backup.mkdir(parents=True)
    files = [FILES[kind] for kind in meta["kinds"]]
    for name in files:
        shutil.copy2(MOTORS / name, backup / name)
    try:
        for name in files:
            atomic_copy(directory / "motorlar" / name, MOTORS / name)
        with tempfile.TemporaryDirectory() as temp:
            for kind in meta["kinds"]:
                execute(kind, meta["date"], meta["center"], snapshot, Path(temp), MOTORS)
        (backup / "etkin.json").write_text(json.dumps({name: digest(MOTORS / name) for name in files}))
        log_change(f"- {backup.name} · {meta['rule']} · {', '.join(files)} · {args.onaylayan}"
                   f" · rapor {directory / 'rapor.md'} · diff {directory / 'kod.diff'} · duman testi başarılı")
    except BaseException:
        for name in files:
            atomic_copy(backup / name, MOTORS / name)
        raise
    print(f"Yerel motorlar etkinleştirildi. Yedek {backup}")


def rollback(args):
    backup = MOTORS / "_yedek" / Path(args.yedek).name
    installed = json.loads((backup / "etkin.json").read_text())
    if installed.keys() - FILES.values() or any(digest(MOTORS / name) != value for name, value in installed.items()):
        raise ValueError("Etkin motorlar yedekten beri değişmiş; geri alma durduruldu.")
    with tempfile.TemporaryDirectory() as temp:
        current = Path(temp)
        for name in installed:
            shutil.copy2(MOTORS / name, current / name)
        try:
            for name in installed:
                atomic_copy(backup / name, MOTORS / name)
            log_change(f"- {datetime.now(ZoneInfo('Europe/Istanbul')).isoformat()} · {backup.name} geri alındı.")
        except BaseException:
            for name in installed:
                atomic_copy(current / name, MOTORS / name)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)
    stage = sub.add_parser("aday")
    for argument in ("girdi", "tarih", "merkez", "cikti", "yamalar", "kural"):
        stage.add_argument("--" + argument, required=True)
    stage.add_argument("--beklenen-depo", action="append", default=[])
    stage.set_defaults(handler=prepare)
    apply = sub.add_parser("uygula")
    for argument in ("aday", "onay", "onaylayan"):
        apply.add_argument("--" + argument, required=True)
    apply.set_defaults(handler=activate)
    undo = sub.add_parser("geri-al")
    undo.add_argument("--yedek", required=True)
    undo.set_defaults(handler=rollback)
    args = parser.parse_args()
    try:
        directory = os.open(MOTORS, os.O_RDONLY)
        try:
            flock(directory, LOCK_EX)
            args.handler(args)
        finally:
            os.close(directory)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
