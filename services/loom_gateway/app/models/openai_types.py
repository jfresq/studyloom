from typing import List, Optional, Literal, Any, Dict
from pydantic import BaseModel
Role = Literal["system", "user", "assistant", "tool"]
class Message(BaseModel):
    role: Role
    content: str
class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = 0.2
    stream: Optional[bool] = False
    loom: Optional[Dict[str, Any]] = None
class ChoiceMessage(BaseModel):
    role: Role
    content: str
class Choice(BaseModel):
    index: int
    message: ChoiceMessage
    finish_reason: str = "stop"
class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
