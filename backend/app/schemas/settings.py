from pydantic import BaseModel, Field


class LLMSettingsUpdateRequest(BaseModel):
    enabled: bool = False
    api_key: str = ""
    base_url: str = Field(default="https://api.openai.com/v1", min_length=1)
    model: str = Field(default="gpt-4.1-mini", min_length=1)
    api_style: str = Field(default="chat_completions", min_length=1)
    timeout_seconds: int = Field(default=45, ge=5, le=180)
