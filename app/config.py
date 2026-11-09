from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    supabase_url: str = ''
    supabase_publishable_key: str = ''
    gemini_api_key: str = ''
    gemini_request_timeout: int = 30
    gemini_chat_model: str = 'gemini-3.5-flash'
    gemini_embed_model: str = 'gemini-embedding-001'
    embed_dim: int = 768
    max_upload_bytes: int = 5 * 1024 * 1024
    max_chunks: int = 40
    min_relevance: float = 0.35
    memory_turns: int = 6
    app_origin: str = 'http://127.0.0.1:8000'

@lru_cache
def settings():
    return Settings()
