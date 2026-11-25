import asyncio
import logging
import os
import uuid
from contextlib import aclosing
from functools import lru_cache

import jwt
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands.models import BedrockModel
from transfer_runs import dispatch
from transfer_chat import explain

app = BedrockAgentCoreApp()
logger = logging.getLogger("tedarik")
MODEL = os.getenv("MODEL_ID", "us.anthropic.claude-opus-5")
REGION = os.getenv("AWS_REGION", "us-east-1")
# AgentCore routes concurrent calls with the same runtime session to the same VM.
active_runs = set()


@lru_cache(maxsize=1)
def signing_keys(issuer):
    return jwt.PyJWKClient(issuer + "/.well-known/jwks.json", timeout=5)


def actor_id(context):
    header = (context.request_headers or {}).get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ValueError("Kimlik doğrulanamadı.")
    issuer = os.environ["COGNITO_ISSUER"]
    key = signing_keys(issuer).get_signing_key_from_jwt(token).key
    claims = jwt.decode(token, key, algorithms=["RS256"], issuer=issuer,
                        options={"require": ["exp", "sub", "token_use", "client_id"], "verify_aud": False})
    if claims["token_use"] != "access" or claims["client_id"] != os.environ["COGNITO_CLIENT_ID"]:
        raise ValueError("Kimlik doğrulanamadı.")
    return str(uuid.UUID(claims["sub"]))


async def explain_events(actor, session, payload):
    events = asyncio.Queue()
    model = BedrockModel(model_id=MODEL, region_name=REGION, max_tokens=4096)
    task = asyncio.create_task(explain(actor, session, payload.get("question"), model,
                                       payload.get("conversation"), on_delta=events.put_nowait))
    task.add_done_callback(lambda _: events.put_nowait(None))
    try:
        yield {"type": "start"}
        while True:
            try:
                event = await asyncio.wait_for(events.get(), timeout=8)
            except TimeoutError:
                yield {"type": "pending"}
                continue
            if event is None:
                break
            yield event
        yield {"type": "transfer", **task.result()}
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@app.entrypoint
async def invoke(payload, context):
    try:
        actor = await asyncio.to_thread(actor_id, context)
        session = str(uuid.UUID(context.session_id))
        if session != context.session_id or not isinstance(payload, dict):
            raise ValueError()
    except (ValueError, TypeError, AttributeError, jwt.PyJWTError):
        yield {"error": "Geçerli bir kullanıcı ve optimizasyon oturumu gerekli."}
        return
    action = payload.get("action")
    if isinstance(action, str) and action in {"prepare", "review_page", "finish", "reopen_review", "status", "download", "explain", "view", "depot"}:
        key = (actor, session)
        writing = action in {"prepare", "finish", "reopen_review"}
        if writing and key in active_runs:
            yield {"error": "Bu optimizasyonun işlemi sürüyor. Durumunu biraz sonra yeniden kontrol edin."}
            return
        if writing:
            active_runs.add(key)
        try:
            if action == "explain":
                async with aclosing(explain_events(actor, session, payload)) as events:
                    async for event in events:
                        yield event
                return
            loop = asyncio.get_running_loop()
            events = asyncio.Queue()

            def on_activity(activity):
                loop.call_soon_threadsafe(events.put_nowait, {"type": "activity", "activity": activity})

            task = asyncio.create_task(asyncio.to_thread(dispatch, actor, session, payload, on_activity if writing else None))

            def on_done(_):
                if writing:
                    active_runs.discard(key)
                events.put_nowait(None)

            task.add_done_callback(on_done)
            yield {"type": "start"}
            while True:
                try:
                    event = await asyncio.wait_for(events.get(), timeout=8)
                except TimeoutError:
                    yield {"type": "pending"}
                    continue
                if event is None:
                    break
                yield event
            yield {"type": "transfer", **task.result()}
        except ValueError as exc:
            yield {"error": str(exc)}
        except Exception as exc:
            logger.error("transfer action=%s error=%s", action, type(exc).__name__)
            yield {"error": "Optimizasyon işlemi tamamlanamadı. Tekrar deneyebilirsiniz."}
        return
    yield {"error": "Bilinmeyen optimizasyon işlemi."}


if __name__ == "__main__":
    app.run()
