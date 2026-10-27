"""Large Language Model (LLM) abstract base class and message representations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional


@dataclass
class LLMMessage:
    """Represents a conversation turn message passed to the LLM."""
    role: str  # "system", "user", "assistant", "tool"
    content: Optional[str] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        return d


@dataclass
class ToolCallDelta:
    """Represents an incrementally streamed tool call."""
    id: str
    name: str
    arguments: str


@dataclass
class LLMResponseChunk:
    """Represents a token or tool invocation chunk yielded by the streaming LLM."""
    delta_text: str = ""
    is_first_token: bool = False
    is_complete: bool = False
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


class LLMProvider(ABC):
    """Abstract interface for swappable LLM providers (e.g. OpenAI, Groq, Anthropic)."""

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[LLMResponseChunk, None]:
        """Streams text chunks and function calls from the LLM."""
        pass
