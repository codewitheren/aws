"""One AgentCore event per completed turn, shared by Strands and the history UI."""
import base64
import json
import os
from datetime import datetime, timezone

from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
from strands.hooks import AgentInitializedEvent, MessageAddedEvent
from strands.types.session import Session, SessionMessage, SessionType


def memory_scope(actor):
    return {"memoryId": os.environ["MEMORY_ID"], "actorId": actor}


def sessions(client, actor, token):
    scope = memory_scope(actor)
    page = client.list_sessions(**scope, maxResults=12, **({"nextToken": token} if token else {}))
    rows = []
    for session in page["sessionSummaries"]:
        sid = session["sessionId"]
        latest = client.list_events(**scope, sessionId=sid, maxResults=1, includePayloads=False)["events"]
        if latest:
            rows.append({"id": sid, "title": base64.urlsafe_b64decode(latest[0]["metadata"]["title"]["stringValue"]).decode(),
                         "createdAt": session["createdAt"].isoformat()})
    return {"type": "sessions", "sessions": rows, "nextToken": page.get("nextToken")}


def read_turns(client, actor, session):
    params = dict(memory_scope(actor), sessionId=session, maxResults=100, includePayloads=True)
    events = []
    while True:
        page = client.list_events(**params)
        events.extend(page["events"])
        if not page.get("nextToken"):
            break
        params["nextToken"] = page["nextToken"]
    turns = []
    for event in sorted(events, key=lambda e: (e["eventTimestamp"], e["eventId"])):
        user, assistant, details = event["payload"]
        turns.append({"prompt": user["conversational"]["content"]["text"],
                      "answer": assistant["conversational"]["content"]["text"],
                      **json.loads(details["blob"])})
    return turns


def transcript(turns):
    messages = []
    for turn in turns:
        messages.append({"role": "user", "text": turn["prompt"]})
        messages.append({"role": "assistant", "text": turn["answer"],
                         "tools": turn["tools"], "sources": turn["sources"]})
    return {"type": "history", "messages": messages, "turn": len(turns)}


def message(role, text):
    return {"role": role, "content": [{"text": text}]}


class ChatSession(AgentCoreMemorySessionManager):
    """Restore completed turns and defer persistence until the model finishes successfully."""

    def __init__(self, actor, session, turns, region):
        self.turns = turns
        config = AgentCoreMemoryConfig(memory_id=os.environ["MEMORY_ID"], actor_id=actor, session_id=session,
                                       retrieval_config={"/preferences/{actorId}/": RetrievalConfig(top_k=5)})
        super().__init__(config, region_name=region)

    def read_session(self, session_id, **kwargs):
        # AgentCore sessions are implicit. Opening an empty chat should create no events.
        return Session(session_id=session_id, session_type=SessionType.AGENT)

    def register_hooks(self, registry, **kwargs):
        registry.add_callback(AgentInitializedEvent, self.restore)
        registry.add_callback(MessageAddedEvent, self.retrieve_customer_context)

    def restore(self, event):
        for turn in self.turns:
            event.agent.messages.append(message("user", turn["prompt"]))
            event.agent.messages.extend(SessionMessage.from_dict(m).to_message() for m in turn["steps"])
            event.agent.messages.append(message("assistant", turn["answer"]))

    def commit(self, prompt, answer, steps, audit):
        details = {"steps": [SessionMessage.from_message(m, i).to_dict() for i, m in enumerate(steps)],
                   "tools": audit.events, "sources": list(audit.sources.values())}
        payload = [{"conversational": {"role": role, "content": {"text": text}}}
                   for role, text in (("USER", prompt), ("ASSISTANT", answer))]
        payload.append({"blob": json.dumps(details, ensure_ascii=False)})
        title = (self.turns[0]["prompt"] if self.turns else prompt).strip()[:48]
        self.memory_client.gmdp_client.create_event(
            **memory_scope(self.config.actor_id), sessionId=self.session_id, payload=payload,
            metadata={"title": {"stringValue": base64.urlsafe_b64encode(title.encode()).decode()}}, eventTimestamp=datetime.now(timezone.utc))
