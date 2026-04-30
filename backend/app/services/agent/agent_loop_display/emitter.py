"""Event emitter for agent loop display."""

import time
import uuid
from typing import List, Dict, Any, Optional

from .event_types import AgentEvent, EventType


class AgentEventEmitter:
    """在Agent循环中发射事件，供前端WebSocket接收"""

    def __init__(self):
        self.events: List[AgentEvent] = []
        self._event_counter = 0

    def emit(self, event: AgentEvent) -> None:
        """发射事件，存入队列供WS发送"""
        self.events.append(event)

    def emit_thinking(self, content: str) -> str:
        """发射思考事件，返回事件ID"""
        event_id = f"think_{self._event_counter}"
        self._event_counter += 1
        self.emit(AgentEvent(
            type=EventType.THINKING,
            id=event_id,
            timestamp=time.time(),
            content=content
        ))
        return event_id

    def emit_tool_call(self, tool_name: str, args: Dict[str, Any]) -> str:
        """发射工具调用事件"""
        event_id = f"tool_{self._event_counter}"
        self._event_counter += 1
        self.emit(AgentEvent(
            type=EventType.TOOL_CALL,
            id=event_id,
            timestamp=time.time(),
            tool_name=tool_name,
            tool_args=args
        ))
        return event_id

    def emit_tool_result(
        self,
        call_id: str,
        result: Any,
        relevance: Optional[float] = None,
        confidence: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> None:
        """发射工具结果事件"""
        self.emit(AgentEvent(
            type=EventType.TOOL_RESULT,
            id=f"{call_id}_result",
            timestamp=time.time(),
            tool_result=result,
            relevance_score=relevance,
            confidence=confidence,
            duration_ms=duration_ms
        ))

    def emit_retrieval_hit(
        self,
        level: str,
        source: str,
        content_preview: str,
        relevance: float,
        confidence: str
    ) -> None:
        """发射检索命中事件"""
        self.emit(AgentEvent(
            type=EventType.RETRIEVAL_HIT,
            id=f"hit_{self._event_counter}",
            timestamp=time.time(),
            level=level,
            content=content_preview,
            relevance_score=relevance,
            confidence=confidence,
            drill_path=[source]
        ))
        self._event_counter += 1

    def emit_decision(self, content: str) -> str:
        """发射决策事件"""
        event_id = f"dec_{self._event_counter}"
        self._event_counter += 1
        self.emit(AgentEvent(
            type=EventType.DECISION,
            id=event_id,
            timestamp=time.time(),
            content=content
        ))
        return event_id

    def emit_ask_user(self, question: str) -> str:
        """发射请求用户输入事件"""
        event_id = f"ask_{self._event_counter}"
        self._event_counter += 1
        self.emit(AgentEvent(
            type=EventType.ASK_USER,
            id=event_id,
            timestamp=time.time(),
            content=question
        ))
        return event_id

    def emit_final_answer(self, content: str) -> None:
        """发射最终答案事件"""
        self.emit(AgentEvent(
            type=EventType.FINAL_ANSWER,
            id=f"final_{self._event_counter}",
            timestamp=time.time(),
            content=content
        ))

    def emit_error(self, content: str) -> None:
        """发射错误事件"""
        self.emit(AgentEvent(
            type=EventType.ERROR,
            id=f"err_{self._event_counter}",
            timestamp=time.time(),
            content=content
        ))

    def get_events(self) -> List[AgentEvent]:
        """获取所有事件"""
        return self.events

    def clear(self) -> None:
        """清空事件队列"""
        self.events.clear()
        self._event_counter = 0