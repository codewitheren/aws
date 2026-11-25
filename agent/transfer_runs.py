"""Persist user-scoped transfer runs using the existing private assets bucket."""
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4
import zipfile

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

PACKAGE = Path(__file__).resolve().parent / "transfer"
CENTERS = {"İzmir","Maltepe","Ankara","Adana","Diyarbakır","Arnavutköy"}
DOWNLOADS = {"transfer.xlsx", "transfer.parquet", "uyarilar.csv", "anomaliler.csv"}
PAGE_SIZE = 10


def read_json(client, bucket, key):
    response = client.get_object(Bucket=bucket, Key=key)
    with response["Body"] as body:
        return json.loads(body.read()), response["ETag"]


def state_for(client, bucket, prefix):
    return optional_json(client, bucket, prefix + "/state.json")


def optional_json(client, bucket, key):
    if not client.list_objects_v2(Bucket=bucket, Prefix=key, MaxKeys=1).get("Contents"):
        return None, None
    try:
        return read_json(client, bucket, key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"NoSuchKey","404"}:
            return None, None
        raise


def commit(client, bucket, prefix, state, version):
    condition = {"IfMatch":version} if version else {"IfNoneMatch":"*"}
    try:
        client.put_object(Bucket=bucket, Key=prefix+"/state.json", Body=json.dumps(state).encode(), **condition)
        return state
    except ClientError as exc:
        if exc.response["ResponseMetadata"]["HTTPStatusCode"] in (409,412):
            return state_for(client, bucket, prefix)[0]
        raise


def run_worker(root, job):
    (root/"job.json").write_text(json.dumps(job))
    proc = subprocess.run([sys.executable, str(PACKAGE/"workflow.py"), str(root)], cwd=root,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900,
                          env={**os.environ, "TRANSFER_RUN_HISTORY_DIR": str(root / "history")})
    if proc.returncode:
        error = root/"error.txt"
        raise ValueError(error.read_text() if error.exists() else "Motor girdileri okunamadı. Kaynak erişimini ve dosya biçimini kontrol edin.")
    return json.loads((root/"result.json").read_text())


def visible(state):
    if not state:
        return {"stage": "empty"}
    private = {"snapshot", "artifacts", "draft", "checks", "findings", "revisions", "changes", "reviewed", "draftLimits", "motorHash", "lastRevert"}
    result = {key: value for key, value in state.items() if key not in private}
    if state["stage"] in ("review", "blocked"):
        if "checks" not in state:
            return dict(result, stage="blocked", legacy=True)
        result.update(review_page(state, 0))
    return result


def review_page(state, offset):
    checks = state.get("checks", [])
    if type(offset) is not int or offset < 0 or offset % PAGE_SIZE or (offset and offset >= len(checks)):
        raise ValueError("Geçersiz bulgu sayfası.")
    end = offset + PAGE_SIZE
    return {"checks": checks[offset:end], "remaining": max(0, len(checks) - end), "offset": offset}


def approved_revisions(state, payload):
    if payload.get("approveOfficial") is not True:
        raise ValueError("Resmi optimizasyon için açık onay gerekli.")
    if state["stage"] == "blocked" or "checks" not in state:
        raise ValueError("Girdileri güncelledikten sonra yeni inceleme başlatın.")
    decisions = payload.get("decisions")
    offset = payload.get("offset", 0)
    review_page(state, offset)
    checks = state["checks"][:offset + PAGE_SIZE]
    if len(checks) < len(state["checks"]) and payload.get("leaveRemaining") is not True:
        raise ValueError("Kalan bulguları inceleyin veya kalan miktarları olduğu gibi bırakmayı onaylayın.")
    required = {c["id"] for c in checks if c["level"] == "uyari"}
    if not isinstance(decisions, dict) or decisions.keys() != required:
        raise ValueError("Gösterilen her uyarı için bir karar gerekli.")
    revisions = {}
    for check in checks:
        decision = decisions.get(check["id"])
        if decision is None:
            continue  # explicit unchanged / acknowledged warning
        edits = check.get("edits", [])
        if not isinstance(decision, list) or len(decision) != len(edits) or not edits:
            raise ValueError("Karar listesi gösterilen bulgunun satırlarıyla eşleşmiyor.")
        for edit, value in zip(edits, decision):
            if value is None:
                continue
            if type(value) not in (int, float) or not 0 <= value < edit["current"]:
                raise ValueError("Miktar mevcut öneriden küçük ve sıfır veya pozitif olmalı.")
            units = value / edit["batch"]
            if not math.isclose(units, round(units), abs_tol=1e-8, rel_tol=0):
                raise ValueError("Miktar sipariş katına uymalı.")
            key = tuple(edit[k].strip().lower() for k in ("depotCode", "productCode"))
            revisions[key] = dict(edit, value=value, approval=f"Kullanıcı onayladı · bulgu {check['id']} · {value:g}")
    return list(revisions.values()), list(decisions)


def download_snapshot(client, bucket, state, root):
    client.download_file(bucket, state["snapshot"], str(root / "snapshot.zip"))
    with zipfile.ZipFile(root / "snapshot.zip") as archive:
        archive.extractall(root / "snapshot")


def day_index(actor, state, kind):
    return f"runs/{actor}/by-date/{state['date']}/{state['center']}/{kind}.json"


def previous_runs(client, bucket, actor, center, day, kind):
    prefix = f"runs/{actor}/by-date/"
    suffix = f"/{center}/{kind}.json"
    dates = set()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            if key.endswith(suffix):
                when = key[len(prefix):-len(suffix)]
                if len(when) == 10 and when < day:
                    dates.add(when)
    return [(when, prefix + when + suffix) for when in sorted(dates, reverse=True)[:3]]


def index_run(client, bucket, actor, state):
    key = day_index(actor, state, state["kind"])
    index = {field: state[field] for field in ("artifacts", "completedAt")}
    for _ in range(5):
        previous, etag = optional_json(client, bucket, key)
        if previous and previous.get("completedAt", "") >= index["completedAt"]:
            return
        try:
            client.put_object(Bucket=bucket, Key=key, Body=json.dumps(index).encode(),
                              **({"IfMatch": etag} if etag else {"IfNoneMatch": "*"}))
            return
        except ClientError as exc:
            if exc.response["ResponseMetadata"]["HTTPStatusCode"] not in (409, 412):
                raise
    raise ValueError("Optimizasyon tamamlandı. Tarih dizini güncellenirken çakışma oldu; tekrar deneyin.")


def cache_history(client, bucket, actor, center, day, kind, root):
    names = {"amb": "Ambient ve Su", "cold": "+4", "ms": "MS"}
    for category in ("ms", "cold") if kind == "ms" else (kind,):
        for when, key in previous_runs(client, bucket, actor, center, day, category):
            index, _ = read_json(client, bucket, key)
            path = root / "history" / when / names[category] / f"{center}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, index["artifacts"] + "/transfer.parquet", str(path))


def dispatch(actor, session, payload):
    client = boto3.client("s3", config=Config(signature_version="s3v4"))
    bucket = os.environ["RUN_BUCKET"]
    prefix = f"runs/{actor}/{session}"
    state, version = state_for(client, bucket, prefix)
    action = payload["action"]
    if action == "status":
        return visible(state)
    if action == "review_page" and state and state["stage"] in ("review", "blocked"):
        return review_page(state, payload.get("offset"))
    if action in {"view", "depot"}:
        if not state or state["stage"] != "ready":
            raise ValueError("Önce optimizasyonu tamamlayın.")
        if action == "view":
            return read_json(client, bucket, state["artifacts"] + "/view.json")[0]
        name = payload.get("name")
        depots = read_json(client, bucket, state["artifacts"] + "/depots.json")[0]
        if not isinstance(name, str) or name not in depots:
            raise ValueError("Depo bu optimizasyonda bulunamadı.")
        return {"depo": name, **depots[name]}
    if action == "download" and state and state["stage"] == "ready":
        name = payload.get("name")
        if not isinstance(name, str) or name not in DOWNLOADS:
            raise ValueError("Dosya bulunamadı.")
        return {"url": client.generate_presigned_url("get_object", Params={"Bucket": bucket,
                "Key": state["artifacts"] + "/" + name, "ResponseContentDisposition": f'attachment; filename="{name}"'}, ExpiresIn=300)}
    if action == "reopen_review" and state:
        if state["stage"] == "review" and state.get("lastRevert"):
            return visible(state)
        if payload.get("approveUndo") is not True or state["stage"] != "ready" or not state.get("revisions"):
            raise ValueError("Revizeleri geri almak için tamamlanmış bir revize ve açık onay gerekli.")
        when = datetime.now(timezone.utc).isoformat()
        log = state["artifacts"] + "/revize_geri_al.json"
        record = {"actor": actor, "when": when, "approval": "Revizeleri geri al ve incelemeye dön",
                  "reverted": state["revisions"]}
        try:
            client.put_object(Bucket=bucket, Key=log, Body=json.dumps(record).encode(), IfNoneMatch="*")
        except ClientError as exc:
            if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 412:
                raise
        state = {k: v for k, v in state.items() if k not in ("artifacts", "summary", "revisions", "reviewed", "completedAt")}
        state.update(stage="review", lastRevert=log)
        return visible(commit(client, bucket, prefix, state, version))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        attempt = prefix + "/" + uuid4().hex
        if action == "prepare":
            if state:
                return visible(state)
            center, kind, raw_date = (payload.get(k) for k in ("center", "kind", "date"))
            if not all(isinstance(v, str) for v in (center, kind, raw_date)):
                raise ValueError("Merkez, kategori ve iş tarihi gerekli.")
            day = date.fromisoformat(raw_date).isoformat()
            if center not in CENTERS or kind not in {"amb", "cold", "ms"} or (center == "Diyarbakır" and kind == "ms"):
                raise ValueError("Merkez veya transfer tipi geçersiz.")
            cache_history(client, bucket, actor, center, day, kind, root)
            review = run_worker(root, dict(action=action, center=center, kind=kind, date=day))
            draft = review.pop("draft")
            blocked = review.pop("blocked")
            state = dict(stage="blocked" if blocked else "review", kind=kind, center=center, date=day, **review)
            if not blocked:
                snapshot = attempt + "/snapshot.zip"
                with zipfile.ZipFile(root / "snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
                    for path in (root / "snapshot").rglob("*"):
                        if path.is_file():
                            archive.write(path, path.relative_to(root / "snapshot"))
                client.upload_file(str(root / "snapshot.zip"), bucket, snapshot)
                draft_key = attempt + "/taslak.parquet"
                client.upload_file(draft, bucket, draft_key)
                state.update(snapshot=snapshot, draft=draft_key)
        elif action == "finish" and state:
            if state["stage"] == "ready":
                if state.get("completedAt"):
                    index_run(client, bucket, actor, state)
                return visible(state)
            revisions, reviewed = approved_revisions(state, payload)
            download_snapshot(client, bucket, state, root)
            result = run_worker(root, dict(state, action="finish", revisions=revisions, reviewed=reviewed))
            for name, path in result["files"].items():
                client.upload_file(path, bucket, attempt + "/" + name)
            client.put_object(Bucket=bucket, Key=attempt + "/depots.json", Body=json.dumps(result["depots"]).encode())
            client.put_object(Bucket=bucket, Key=attempt + "/view.json", Body=json.dumps(result["view"]).encode())
            state.update(stage="ready", artifacts=attempt, summary=result["summary"], revisions=revisions,
                         reviewed=reviewed, completedAt=datetime.now(timezone.utc).isoformat())
        else:
            raise ValueError("Bu işlem için geçerli bir optimizasyon gerekli.")
        saved = commit(client, bucket, prefix, state, version)
        if action == "finish" and saved and saved.get("completedAt"):
            index_run(client, bucket, actor, saved)
        return visible(saved)
