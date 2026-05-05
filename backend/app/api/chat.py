"""Chat sessions and message API."""

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.config import settings
from app.models.database import get_connection
from app.models.crud import load_model_configs
from app.models.router import ModelRouter
from app.models.config import RoleType
from app.services.llm.client import LLMClient
from app.services.agent.loop import AgentLoop
from app.services.agent.context import AgentContext
from app.services.agent.registry import ToolRegistry
from app.services.agent.tools import register_all_tools
from app.services.agent.kb_state import KBCompilationState
from app.services.agent.output_store import ToolOutputStore

router = APIRouter(prefix="/api", tags=["chat"])


class CreateSessionRequest(BaseModel):
    kb_id: str
    title: str = "新对话"


class SendMessageRequest(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str


class SessionResponse(BaseModel):
    id: str
    kb_id: str
    title: str
    created_at: str


def _build_agent(kb_id: str, llm_client: LLMClient, router_obj: ModelRouter) -> tuple[AgentLoop, ToolRegistry, KBCompilationState]:
    """Build an AgentLoop with tools registered for the KB's compilation state.

    Returns (agent, registry, kb_state) so callers can construct AgentContext.
    """
    registry = ToolRegistry()
    embedding_provider = router_obj.get_provider(RoleType.EMBEDDING)
    kb_state = KBCompilationState.check(kb_id)
    register_all_tools(registry, kb_id, embedding_provider, kb_state=kb_state, llm_client=llm_client)
    agent = AgentLoop(llm_client, registry, max_iterations=settings.agent_max_iterations)
    return agent, registry, kb_state


async def _run_agent_query(content: str, kb_id: str) -> str:
    """Run the agent loop and return the final answer (non-streaming, no ask_user)."""
    db_configs = load_model_configs()
    if not db_configs:
        raise RuntimeError("No model configuration found")

    router_obj = ModelRouter()
    router_obj.register(db_configs)
    llm_client = LLMClient(router_obj)
    agent, _registry, _kb_state = _build_agent(kb_id, llm_client, router_obj)

    final_answer = "No response generated."
    async for event in agent.run(user_query=content, kb_id=kb_id):
        if event["type"] == "final_answer":
            answer = event.get("content", "")
            if answer and answer.strip():
                final_answer = answer

    # Cleanup stale externalized tool outputs
    try:
        store = ToolOutputStore(kb_id, "")
        store.cleanup_stale()
    except Exception:
        pass

    return final_answer


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(data: CreateSessionRequest):
    """Create a new chat session for a knowledge base."""
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT id FROM knowledge_bases WHERE id = ?", (data.kb_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Knowledge base not found")
    finally:
        conn.close()

    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO sessions (id, kb_id, title) VALUES (?, ?, ?)",
            (session_id, data.kb_id, data.title),
        )
        conn.commit()
    finally:
        conn.close()

    return SessionResponse(
        id=session_id,
        kb_id=data.kb_id,
        title=data.title,
        created_at=datetime.now().isoformat(),
    )


@router.get("/sessions/{kb_id}", response_model=list[SessionResponse])
async def list_sessions(kb_id: str):
    """List all sessions for a knowledge base."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT id, kb_id, title, created_at FROM sessions WHERE kb_id = ? ORDER BY created_at DESC",
            (kb_id,),
        )
        rows = cursor.fetchall()
        return [
            SessionResponse(
                id=row["id"],
                kb_id=row["kb_id"],
                title=row["title"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
    finally:
        conn.close()


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(session_id: str):
    """List all messages in a session."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT id, session_id, role, content, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        rows = cursor.fetchall()
        return [
            MessageResponse(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
    finally:
        conn.close()


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
async def send_message(session_id: str, data: SendMessageRequest):
    """Send a message and get a response (non-streaming)."""
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT kb_id FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        kb_id = row["kb_id"]
    finally:
        conn.close()

    # Save user message
    user_msg_id = f"msg_{uuid.uuid4().hex[:8]}"
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, 'user', ?)",
            (user_msg_id, session_id, data.content),
        )
        conn.commit()
    finally:
        conn.close()

    # Run agent
    response = await _run_agent_query(data.content, kb_id)

    # Save assistant message
    assistant_msg_id = f"msg_{uuid.uuid4().hex[:8]}"
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, 'assistant', ?)",
            (assistant_msg_id, session_id, response),
        )
        conn.commit()
    finally:
        conn.close()

    return MessageResponse(
        id=assistant_msg_id,
        session_id=session_id,
        role="assistant",
        content=response,
        created_at=datetime.now().isoformat(),
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str):
    """Delete a session and its messages."""
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()

    return None


@router.put("/sessions/{session_id}/title")
async def update_session_title(session_id: str):
    """Auto-generate title from first user message (max 20 chars)."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT content FROM messages WHERE session_id = ? AND role = 'user' ORDER BY created_at ASC LIMIT 1",
            (session_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No messages found")

        content = row["content"]
        title = content[:20] + ("..." if len(content) > 20 else "")

        conn.execute(
            "UPDATE sessions SET title = ? WHERE id = ?",
            (title, session_id),
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT id, kb_id, title, created_at FROM sessions WHERE id = ?",
            (session_id,),
        )
        s = cursor.fetchone()
        return SessionResponse(
            id=s["id"], kb_id=s["kb_id"], title=s["title"],
            created_at=s["created_at"],
        )
    finally:
        conn.close()


@router.websocket("/ws/sessions/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    """WebSocket endpoint with bidirectional ask_user support.

    Protocol:
      - Client → Server: {"content": "..."} for user questions
      - Client → Server: {"type": "user_response", "answer": "..."} for ask_user replies
      - Server → Client: agent events (thinking, tool_call, ask_user, final_answer, etc.)
    """
    await websocket.accept()

    conn = get_connection()
    try:
        cursor = conn.execute("SELECT kb_id FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        if not row:
            await websocket.close(code=4004, reason="Session not found")
            return
        kb_id = row["kb_id"]
    finally:
        conn.close()

    # Load history messages for multi-turn context (optimized)
    # Only load recent exchanges + all system messages (turn summaries)
    history_messages: list[dict] = []
    conn = get_connection()
    try:
        # Load all system messages (turn summaries) — they're compact context
        cursor = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? AND role = 'system' ORDER BY created_at ASC",
            (session_id,),
        )
        system_msgs = [{"role": row["role"], "content": row["content"]} for row in cursor.fetchall()]

        # Load last 2 user-assistant exchanges (recent context)
        cursor = conn.execute(
            """SELECT role, content FROM (
                SELECT role, content, created_at FROM messages
                WHERE session_id = ? AND role IN ('user', 'assistant')
                ORDER BY created_at DESC LIMIT 4
            ) ORDER BY created_at ASC""",
            (session_id,),
        )
        recent_msgs = [{"role": row["role"], "content": row["content"]} for row in cursor.fetchall()]

        # Combine: system summaries (compact) + recent exchanges (verbatim)
        history_messages = system_msgs + recent_msgs
    finally:
        conn.close()

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)

            # Handle user_response (ask_user reply) — processed inline during agent loop
            msg_type = message_data.get("type", "")
            if msg_type == "user_response":
                # This should not happen outside of an active ask_user handshake;
                # ignore and continue waiting for a proper user question.
                continue

            content = message_data.get("content", "")
            if not content:
                continue

            # Save user message
            user_msg_id = f"msg_{uuid.uuid4().hex[:8]}"
            conn = get_connection()
            try:
                conn.execute(
                    "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, 'user', ?)",
                    (user_msg_id, session_id, content),
                )
                conn.commit()
            finally:
                conn.close()

            # Build agent and context
            db_configs = load_model_configs()
            if not db_configs:
                await websocket.send_text(json.dumps({"type": "error", "content": "No model configuration"}, ensure_ascii=False))
                continue

            router_obj = ModelRouter()
            router_obj.register(db_configs)
            llm_client = LLMClient(router_obj)
            agent, registry, kb_state = _build_agent(kb_id, llm_client, router_obj)

            # Query total document count for DecisionPointManager
            total_docs = 1
            conn = get_connection()
            try:
                cursor = conn.execute(
                    "SELECT COUNT(*) as cnt FROM documents WHERE kb_id = ?",
                    (kb_id,),
                )
                row = cursor.fetchone()
                if row:
                    total_docs = row["cnt"] or 1
            finally:
                conn.close()

            # Shared state for ask_user handshake
            pending_ask_answer: str = ""

            async def ask_user_cb(_data: dict) -> str:
                """Return the answer already received by the WebSocket handler."""
                return pending_ask_answer or "用户未回复，请基于已有信息继续分析。"

            agent_ctx = AgentContext(
                kb_id=kb_id,
                session_id=session_id,
                model_router=llm_client,
                tool_registry=registry,
                embedding_provider=router_obj.get_provider(RoleType.EMBEDDING),
                max_iterations=settings.agent_max_iterations,
                ask_user_callback=ask_user_cb,
                history_messages=history_messages,
                kb_state=kb_state,
                metadata={"total_docs": total_docs},
            )

            # Stream agent events with bidirectional ask_user
            full_response = ""
            agent_error = None
            turn_summary_data: dict = {}
            try:
                async for event in agent.run(ctx=agent_ctx, user_query=content):
                    await websocket.send_text(json.dumps(event, ensure_ascii=False))

                    if event["type"] == "ask_user":
                        # Agent yielded ask_user event; it will call ask_user_cb next.
                        # Wait for frontend to send its answer.
                        try:
                            raw = await websocket.receive_text()
                            resp = json.loads(raw)
                            pending_ask_answer = resp.get("answer", resp.get("content", ""))
                        except WebSocketDisconnect:
                            pending_ask_answer = "用户已断开连接"

                    if event["type"] == "final_answer":
                        full_response = event["content"]
                    elif event["type"] == "error":
                        agent_error = event.get("content", "Agent execution error")
                    elif event["type"] == "turn_summary":
                        turn_summary_data = event
            except Exception as agent_exc:
                agent_error = str(agent_exc)

            # Cleanup stale externalized tool outputs after each turn
            try:
                store = ToolOutputStore(kb_id, session_id)
                store.cleanup_stale()
            except Exception:
                pass

            # Guarantee: always emit terminal event if none was sent
            if not full_response and not agent_error:
                agent_error = "Agent 未生成回复，请重试或尝试其他问题"
                await websocket.send_text(json.dumps({"type": "error", "content": agent_error}, ensure_ascii=False))

            # Persist inter-turn context summary as a system message
            if turn_summary_data:
                entities = turn_summary_data.get("entities_discovered", [])
                relations = turn_summary_data.get("relations_discovered", [])
                docs_read = turn_summary_data.get("docs_read", [])
                summary_text = (
                    f"[本轮搜索摘要]\n"
                    f"已发现实体 ({len(entities)}): {', '.join(entities[:20])}\n"
                    f"已发现关系 ({len(relations)}): {', '.join(relations[:10])}\n"
                    f"已读取文档 ({len(docs_read)}): {', '.join(docs_read[:10])}"
                )
                conn = get_connection()
                try:
                    conn.execute(
                        "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, 'system', ?)",
                        (f"msg_{uuid.uuid4().hex[:8]}", session_id, summary_text),
                    )
                    conn.commit()
                except Exception:
                    pass
                finally:
                    conn.close()
                # Add to history for next turn
                history_messages.append({"role": "system", "content": summary_text})

            # Save assistant message
            if full_response:
                assistant_msg_id = f"msg_{uuid.uuid4().hex[:8]}"
                conn = get_connection()
                try:
                    conn.execute(
                        "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, 'assistant', ?)",
                        (assistant_msg_id, session_id, full_response),
                    )
                    conn.commit()
                finally:
                    conn.close()

            # Update history for next turn
            history_messages.append({"role": "user", "content": content})
            if full_response:
                history_messages.append({"role": "assistant", "content": full_response})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False))
        except Exception:
            pass
