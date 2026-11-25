"""Evidence tools for the Strands analyst. Official writes stay in the run API."""
import asyncio
from datetime import date
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

import boto3
from botocore.config import Config
import pandas as pd
from strands import Agent, tool
from strands.types.exceptions import MaxTokensReachedException

from transfer_runs import (PACKAGE, day_index, download_snapshot, optional_json, previous_runs,
                           read_json, review_page, run_worker, state_for)
# The transfer modules also run directly as command-line programs.
sys.path.insert(0, str(PACKAGE))
from analytics import history, query
from calistir import varsayilan_parametreler
from preflight import CATEGORIES, history_paths
from surucu import _norm


def parquet(client, bucket, key):
    with client.get_object(Bucket=bucket, Key=key)["Body"] as body:
        return pd.read_parquet(BytesIO(body.read()))


async def explain(actor, session, question, model, conversation=None):
    if not isinstance(question, str) or not 0 < len(question.strip()) <= 2000:
        raise ValueError("1–2000 karakterlik bir soru gerekli.")
    messages = []
    if conversation is not None:
        if not isinstance(conversation, list) or len(conversation) > 3:
            raise ValueError("Geçersiz konuşma geçmişi.")
        for turn in conversation:
            if not isinstance(turn, dict) or not all(
                isinstance(turn.get(field), str) and len(turn[field]) <= limit
                for field, limit in (("question", 2000), ("answer", 5000))
            ):
                raise ValueError("Geçersiz konuşma geçmişi.")
            for role, field in (("user", "question"), ("assistant", "answer")):
                messages.append({"role": role, "content": [{"text": turn[field]}]})
    bucket = os.environ["RUN_BUCKET"]
    client = boto3.client("s3", config=Config(signature_version="s3v4"))
    prefix = f"runs/{actor}/{session}"
    state, _ = await asyncio.to_thread(state_for, client, bucket, prefix)
    if not state:
        raise ValueError("Önce girdileri kontrol edin.")
    center, day, selected = (state[k] for k in ("center", "date", "kind"))
    scoped = {}
    prior_cache = {}

    def previous(kind):
        if kind not in prior_cache:
            prior_cache[kind] = previous_runs(client, bucket, actor, center, day, kind)
        return prior_cache[kind]

    def read_category(kind, when, archive_only=False):
        cache_key = (kind, when, archive_only)
        if cache_key in scoped:
            return scoped[cache_key]
        key, origin = None, None
        if kind == selected and when in ("", day) and not archive_only:
            if state.get("artifacts"):
                key, origin = state["artifacts"] + "/transfer.parquet", "resmi"
            elif state.get("draft"):
                key, origin = state["draft"], "taslak"
        if not key and not archive_only:
            lookup = dict(state, date=when or day)
            index, _ = optional_json(client, bucket, day_index(actor, lookup, kind))
            if index:
                key, origin = index["artifacts"] + "/transfer.parquet", "resmi"
        if key:
            result = parquet(client, bucket, key), {"kosu": origin, "tarih": when or day, "dosya": "transfer.parquet"}
        else:
            upper = when or day
            paths = history_paths(center, upper, kind, limit=365, include_day=bool(when) or archive_only)
            if when or archive_only:
                paths = [(d, p) for d, p in paths if d == upper]
            older = previous(kind) if not when and not archive_only else []
            if older and (not paths or older[0][0] >= paths[0][0]):
                archived, index_key = older[0]
                pointer, _ = read_json(client, bucket, index_key)
                result = parquet(client, bucket, pointer["artifacts"] + "/transfer.parquet"), {
                    "kosu": "resmi", "tarih": archived, "dosya": "transfer.parquet"}
            elif paths:
                d, p = paths[0]
                result = pd.read_parquet(p), {"kosu": "arşiv", "tarih": d, "dosya": p.name}
            else:
                result = None, {"eksik": True, "tarih": when or day}
        scoped[cache_key] = result
        return result

    def arguments(category, when=""):
        if category and category not in CATEGORIES:
            raise ValueError("Kategori amb, cold veya ms olmalı.")
        if when:
            date.fromisoformat(when)
        return [category] if category else CATEGORIES

    @tool
    def metrik_sorgu(kategori: str = "", depo: str = "", urun: str = "", depo_tipi: str = "",
                    tarih: str = "", nedenler: bool = False, arsiv: bool = False) -> dict:
        """Parquet'ten miktar, kısma oranı, satır C/P, doluluk ve gerekçeleri hesapla. Kategori amb/cold/ms; boşsa üçünü sorgular. Ürün tam ad, kısmi ad veya kod olabilir. Tarih YYYY-MM-DD. arsiv=true yalnız ilgili günün canlı arşiv çıktısını okur."""
        try:
            data = {}
            for kind in arguments(kategori, tarih):
                frame, source = read_category(kind, tarih, arsiv)
                stats = query(kind, frame, depo, urun, depo_tipi, nedenler) if frame is not None else {}
                data[kind] = {"kategori": CATEGORIES[kind], "kaynak": source, **stats}
            return {"merkez": center, "kategoriler": data}
        except ValueError as exc:
            return {"hata": str(exc)}

    @tool
    def gecmisle_kiyas(kategori: str = "", depo: str = "", depo_tipi: str = "") -> dict:
        """Bugünkü resmi veya taslak koşuyu, aynı kategori ve merkezde önceki en fazla üç arşiv günüyle karşılaştır."""
        try:
            data = {}
            for kind in arguments(kategori):
                frame, source = read_category(kind, "")
                if frame is not None and source["kosu"] in ("resmi", "taslak") and source["tarih"] == day:
                    prior = [(d, read_category(kind, d)[0])
                             for d, _ in previous(kind)]
                    data[kind] = dict(history(kind, center, day, frame, depo, depo_tipi, prior), bugununKaynagi=source)
                else:
                    data[kind] = {"eksik": "Güncel resmi veya taslak çıktı yok."}
            return {"merkez": center, "tarih": day, "kategoriler": data}
        except ValueError as exc:
            return {"hata": str(exc)}

    @tool
    def inceleme_bulgulari(sayfa: int = 1) -> dict:
        """Sıradaki en fazla 10 koşu öncesi kontrolü ve onaylanmış revize sonuçlarını oku. Sayfa 1 ile başlar."""
        try:
            page = review_page(state, (sayfa - 1) * 10)
        except ValueError as exc:
            return {"hata": str(exc)}
        return {"asama": state["stage"], **page, "revizeler": state.get("summary", {}).get("revised", [])[:10]}

    @tool
    def relex_revize_kaydi(depo: str = "", urun: str = "") -> dict:
        """Bu koşuda onaylanan revizenin ilk Relex miktarını, uygulanan miktarı, kanıtını ve kararını döndürür."""
        records = []
        for row in state.get("revisions", []):
            if (not depo or _norm(depo) in _norm(row["depot"]) or _norm(depo) == _norm(row["depotCode"])) and (
                not urun or _norm(urun) in _norm(row["product"]) or _norm(urun) == _norm(row["productCode"])
            ):
                records.append(row)
        return {"kaynak": "revize_log.csv / eski_miktar, yeni_miktar, kanit, onay", "toplam": len(records), "revizeler": records[:10]}

    @tool
    def kosu_uyarilari(arama: str = "") -> dict:
        """Resmi motorun sonuc.json kontrol listesinden en fazla 10 eşleşme getir."""
        alerts = [alert for alert in state.get("summary", {}).get("alerts", [])
                  if _norm(arama) in _norm(f"{alert['name']} {alert['evidence']}")]
        return {"kaynak": "sonuc.json / kontrol", "toplam": len(alerts), "uyarilar": alerts[:10]}

    @tool
    def motor_parametreleri() -> dict:
        """Seçili transfer motorunun ayarlanabilir parametre adlarını ve varsayılanlarını döndürür."""
        return {"kategori": selected, "kaynak": "motorlar / üst düzey atamalar", "parametreler": varsayilan_parametreler(selected)}

    @tool
    def senaryo_kos(degisiklik_tipi: str, deger: str, alan: str = "", depo: str = "", urun: str = "",
                    kategori: str = "", ek_degisiklikler: str = "") -> dict:
        """İstenen what-if'i resmi/taslak kopyada çalıştır. Tip parametre/buffer/sharing/tir/relex/kampanya; değer JSON metni (1.2, 15, true veya ["kod"]). Buffer %120 = 1.2. Parametre/sharing/kampanya için alan; relex için depo ve ürün. Açıkça istenen birleşik senaryoda ek_degisiklikler, type/value/field/depot/product anahtarlarıyla JSON liste olabilir."""
        try:
            kind = kategori or selected
            arguments(kind)
            base = state
            if kind != selected:
                pointer, _ = optional_json(client, bucket, day_index(actor, state, kind))
                base, _ = state_for(client, bucket, pointer["artifacts"].rsplit("/", 1)[0]) if pointer else (None, None)
            if not base or not base.get("snapshot") or not base.get("motorHash"):
                return {"hata": "Bu kategoride senaryo için eşleşen güncel girdi kopyası yok."}
            baseline = base["artifacts"] + "/transfer.parquet" if base.get("artifacts") else base.get("draft")
            if not baseline:
                return {"hata": "Bu koşunun resmi veya taslak çıktısı yok."}
            change = dict(type=degisiklik_tipi, value=json.loads(deger), field=alan, depot=depo, product=urun)
            additional = json.loads(ek_degisiklikler) if ek_degisiklikler else []
            if not isinstance(additional, list) or any(not isinstance(item, dict) for item in additional):
                return {"hata": "Ek değişiklikler JSON nesneleri listesi olmalı."}
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                download_snapshot(client, bucket, base, root)
                client.download_file(bucket, baseline, str(root / "baseline.parquet"))
                result = run_worker(root, dict(base, action="scenario", change=[change, *additional]))
                scenario_id = uuid4().hex
                for name, path in result.pop("files").items():
                    client.upload_file(path, bucket, f"{prefix}/whatif/{scenario_id}/motor/{name}")
            result["kaynak"] = {"referans": "resmi" if base.get("artifacts") else "taslak", "tarih": day, "kategori": kind}
            client.put_object(Bucket=bucket, Key=f"{prefix}/whatif/{scenario_id}/sonuc.json", Body=json.dumps(result).encode())
            return result
        except ValueError as exc:
            return {"hata": str(exc)}

    tools = [metrik_sorgu, gecmisle_kiyas, inceleme_bulgulari, relex_revize_kaydi,
             kosu_uyarilari, motor_parametreleri, senaryo_kos]
    agent = Agent(model=model, system_prompt=(PACKAGE / "SKILL.md").read_text(), tools=tools, messages=messages, callback_handler=None)
    context = dict(merkez=center, tarih=day, secili_kategori=selected, asama=state["stage"])
    try:
        result = await agent.invoke_async(
            f"Koşu bağlamı: {json.dumps(context, ensure_ascii=False)}\nKullanıcının sorusu: {question}",
            limits={"turns": 7},
        )
    except MaxTokensReachedException:
        return {"answer": "Yanıt sınırına ulaşıldı. Bir depo, ürün veya metrikle tekrar sorabilirsiniz."}
    return {"answer": str(result)}
