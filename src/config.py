from functools import lru_cache
from pathlib import Path
from typing import Optional

import os

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv(Path(".env"))


class Settings(BaseSettings):
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    supabase_url: Optional[str] = Field(default=None, alias="SUPABASE_URL")
    supabase_key: Optional[str] = Field(default=None, alias="SUPABASE_KEY")
    app_user_id: str = Field(default="local-user", alias="APP_USER_ID")

    model_config = SettingsConfigDict(extra="ignore")

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


@lru_cache
def get_settings() -> Settings:
    import streamlit as st
    import os
    
    def get_val(key_name: str) -> Optional[str]:
        # 1. Intelligently attempt Streamlit Secrets first (Production Source of Truth)
        try:
            if key_name in st.secrets:
                val = st.secrets[key_name]
                if val:
                    return str(val).strip()
        except Exception:
            pass
            
        # 2. Fall back to Local Environment Variables (.env)
        val = os.getenv(key_name)
        if val:
            return str(val).strip()
            
        return None

    return Settings(
        openai_api_key=get_val("OPENAI_API_KEY"),
        openai_model=get_val("OPENAI_MODEL") or "gpt-4o-mini",
        supabase_url=get_val("SUPABASE_URL"),
        supabase_key=get_val("SUPABASE_KEY"),
        app_user_id=get_val("APP_USER_ID") or "local-user",
    )
