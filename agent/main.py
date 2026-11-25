import asyncio
import logging
import os
import uuid
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


@app.entrypoint
async def invoke(payload, context):
    try:
        actor = await asyncio.to_thread(actor_id, context)
        session = str(uuid.UUID(context.session_id))
        if session != context.session_id or not isinstance(payload, dict):
            raise ValueError()
    except (ValueError, TypeError, AttributeError, jwt.PyJWTError):
        yield {"error": "Geçerli bir kullanıcı ve koşu oturumu gerekli."}
        return
    action = payload.get("action")
    if isinstance(action, str) and action in {"prepare", "review_page", "finish", "reopen_review", "status", "download", "explain"}:
        key = (actor, session)
        writing = action in {"prepare", "finish", "reopen_review"}
        if writing and key in active_runs:
            yield {"error": "Bu koşunun işlemi sürüyor. Durumunu biraz sonra yeniden kontrol edin."}
            return
        if writing:
            active_runs.add(key)
        try:
            if action == "explain":
                task = asyncio.create_task(explain(actor, session, payload.get("question"),
                    BedrockModel(model_id=MODEL, region_name=REGION, max_tokens=4096), payload.get("conversation")))
            else:
                task = asyncio.create_task(asyncio.to_thread(dispatch, actor, session, payload))
            if writing:
                task.add_done_callback(lambda _: active_runs.discard(key))
            yield {"type": "start"}
            while not task.done():
                await asyncio.wait({task}, timeout=8)
                if not task.done():
                    yield {"type": "pending"}
            yield {"type": "transfer", **task.result()}
        except ValueError as exc:
            yield {"error": str(exc)}
        except Exception as exc:
            logger.error("transfer action=%s error=%s", action, type(exc).__name__)
            yield {"error": "Koşu işlemi tamamlanamadı. Tekrar deneyebilirsiniz."}
        return
    yield {"error": "Bilinmeyen koşu işlemi."}


if __name__ == "__main__":
    app.run()
