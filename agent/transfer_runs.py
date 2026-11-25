"""Persist user-scoped transfer runs using the existing private assets bucket."""
import json
import math
import os
import re
import unicodedata
from datetime import date
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
DOWNLOADS = {"transfer.xlsx","uyarilar.csv","anomaliler.csv"}


def read_json(client, bucket, key):
    response = client.get_object(Bucket=bucket, Key=key)
    with response["Body"] as body:
        return json.loads(body.read()), response["ETag"]


def state_for(client, bucket, prefix):
    key = prefix + "/state.json"
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
                          env={**os.environ, "PYTHONPATH":os.pathsep.join([str(PACKAGE.parent), os.environ.get("PYTHONPATH","")])})
    if proc.returncode:
        error = root/"error.txt"
        raise ValueError(error.read_text() if error.exists() else "Motor girdileri okunamadı. Kaynak erişimini ve dosya biçimini kontrol edin.")
    return json.loads((root/"result.json").read_text())


def visible(state):
    if not state:
        return {"stage":"empty"}
    return {k:v for k,v in state.items() if k not in {"snapshot","artifacts"}}


def changes_for(findings, values):
    options = {str(f["row"]):f for f in findings}
    if not isinstance(values, dict) or values.keys() - options.keys():
        raise ValueError("Karar listesi bu koşuya ait değil.")
    for row, value in values.items():
        f = options[row]
        if type(value) not in (int,float) or not math.isfinite(value) or not 0 <= value < f["current"]:
            raise ValueError("Miktar mevcut öneriden küçük ve sıfır veya pozitif olmalı.")
        batches = value/f["batch"]
        if not math.isclose(batches, round(batches), abs_tol=1e-8, rel_tol=0):
            raise ValueError("Miktar sipariş katına uymalı.")
    return values


def dispatch(actor, session, payload):
    client = boto3.client("s3", config=Config(signature_version="s3v4"))
    bucket = os.environ["RUN_BUCKET"]
    prefix = f"runs/{actor}/{session}"
    state, version = state_for(client,bucket,prefix)
    action = payload["action"]
    if action == "status":
        return visible(state)
    if action == "download" and state and state["stage"] == "ready":
        name = payload.get("name")
        if name not in DOWNLOADS:
            raise ValueError("Dosya bulunamadı.")
        return {"url":client.generate_presigned_url("get_object", Params={"Bucket":bucket,
                "Key":state["artifacts"]+"/"+name,"ResponseContentDisposition":f'attachment; filename="{name}"'}, ExpiresIn=300)}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        attempt = prefix + "/" + uuid4().hex
        if action == "prepare":
            if state:
                return visible(state)
            center, kind = payload.get("center"), payload.get("kind")
            day = date.fromisoformat(payload.get("date","")).isoformat()
            if center not in CENTERS or kind not in {"amb","cold","ms"} or (center == "Diyarbakır" and kind == "ms"):
                raise ValueError("Merkez veya transfer tipi geçersiz.")
            review = run_worker(root, dict(action=action, center=center, kind=kind))
            snapshot = attempt + "/snapshot.zip"
            with zipfile.ZipFile(root/"snapshot.zip","w",zipfile.ZIP_DEFLATED) as archive:
                for path in (root/"snapshot").rglob("*"):
                    if path.is_file():
                        archive.write(path,path.relative_to(root/"snapshot"))
            client.upload_file(str(root/"snapshot.zip"),bucket,snapshot)
            state = dict(stage="review",snapshot=snapshot,kind=kind,date=day,**review)
        elif action == "finish" and state:
            if state["stage"] == "ready":
                return visible(state)
            changes = changes_for(state["findings"],payload.get("changes"))
            client.download_file(bucket,state["snapshot"],str(root/"snapshot.zip"))
            with zipfile.ZipFile(root/"snapshot.zip") as archive:
                archive.extractall(root/"snapshot")
            result = run_worker(root, dict(**state,action="finish",changes=changes))
            for name,path in result["files"].items():
                client.upload_file(path,bucket,attempt+"/"+name)
            client.put_object(Bucket=bucket, Key=attempt+"/depots.json",Body=json.dumps(result["depots"]).encode())
            state.update(stage="ready", artifacts=attempt, summary=result["summary"], changes=changes)
        else:
            raise ValueError("Bu işlem için geçerli bir koşu gerekli.")
        return visible(commit(client,bucket,prefix,state,version))


def search_text(value):
    value = unicodedata.normalize("NFKD", value.casefold().replace("ı", "i"))
    return "".join(char for char in value if not unicodedata.combining(char))


def depot_cut_answer(question, depots, state):
    query = search_text(question)
    if not re.search(r"\b(?:kisma|kesinti)\s+oran\w*", query):
        return None
    if re.search(r"\b(?:neden|niye|nicin|sebeb\w*|gerekce\w*|karsilastir\w*|gecmis|dun|hafta\w*|trend)\b", query):
        return None
    # Allow Turkish locative suffixes and require a full depot name match.
    matches = []
    for name in depots:
        pattern = r"(?<!\w)" + re.escape(search_text(name)) + r"(?:['’]?(?:da|de|ta|te))?(?!\w)"
        match = re.search(pattern, query)
        if match:
            matches.append((name, match.span()))
    names = [name for name, (start, end) in matches if not any(
        other_start <= start and end <= other_end and (start, end) != (other_start, other_end)
        for _, (other_start, other_end) in matches
    )]
    if len(names) != 1:
        return None
    name = names[0]
    for label, value, unit, *_ in depots[name].get("kpi", []):
        if unit == "%" and label.startswith("Kesinti oranı") and isinstance(value, (float, int)):
            rate = f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")
            basis = "adet bazında, dökme hariç" if state["kind"] == "ms" else "adet bazında"
            return (f"{name} deposunun kısma oranı %{rate} ({basis}).\n\n"
                    f"{state['center']} · {state['date']} · Kaynak: motorun depo KPI’ı.")
    return None


async def explain(actor, session, question, model):
    import asyncio
    from strands import Agent, tool
    from strands.types.exceptions import MaxTokensReachedException

    if not isinstance(question,str) or not 0 < len(question.strip()) <= 2000:
        raise ValueError("1–2000 karakterlik bir soru gerekli.")
    bucket = os.environ["RUN_BUCKET"]
    client = boto3.client("s3", config=Config(signature_version="s3v4"))
    state, _ = await asyncio.to_thread(state_for,client,bucket,f"runs/{actor}/{session}")
    if not state or state["stage"] != "ready":
        raise ValueError("Önce koşuyu tamamlayın.")
    depots, _ = await asyncio.to_thread(read_json,client,bucket,state["artifacts"]+"/depots.json")
    answer = depot_cut_answer(question, depots, state)
    if answer:
        return {"answer": answer}

    @tool
    def depo_kaniti(depo: str) -> dict:
        """Motorun ilgili depoya ait kesinti gerekçelerini ve doluluk kanıtını getir."""
        query = search_text(depo.strip())
        matches = [key for key in depots if query == search_text(key)]
        if not matches and query:
            matches = [key for key in depots if query in search_text(key)]
        if len(matches) == 1:
            return {"depo":matches[0],"kaynak":"sonuc.json / detay.depolar","kanit":depots[matches[0]]}
        return {"eslesen_depolar":matches[:25]}

    summary = state["summary"]

    @tool
    def kosu_uyarilari(arama: str) -> dict:
        """Get up to ten run warnings matching a name or phrase. Pass an empty string for the first warnings."""
        query = search_text(arama.strip())
        alerts = [alert for alert in summary.get("alerts", [])
                  if query in search_text(f"{alert['name']} {alert['evidence']}")]
        return {"toplam": len(alerts), "uyarilar": alerts[:10]}

    agent = Agent(model=model, system_prompt=(PACKAGE/"SKILL.md").read_text(),
                  tools=[depo_kaniti, kosu_uyarilari], callback_handler=None)
    context = json.dumps({k: v for k, v in summary.items() if k != "alerts"}, ensure_ascii=False)
    try:
        result = await agent.invoke_async(
            f"Koşu kaynağı: sonuc.json ve ana parquet\n{context}\nKullanıcının sorusu: {question}",
            limits={"turns": 5},
        )
    except MaxTokensReachedException:
        return {"answer": "Yanıt çıktı sınırına ulaştı. Soruyu bir depo ve bir metrikle sınırlandırıp tekrar sorabilirsiniz."}
    return {"answer":str(result)}
