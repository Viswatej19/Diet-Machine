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
    
    # Base dictionary of keys to check
    keys_map = {
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_MODEL": "openai_model",
        "SUPABASE_URL": "supabase_url",
        "SUPABASE_KEY": "supabase_key",
        "APP_USER_ID": "app_user_id"
    }
    
    extracted_kwargs = {}
    for env_key, kwarg_key in keys_map.items():
        # 1. Try OS / Dotenv
        val = os.getenv(env_key)
        
        # 2. Try Streamlit Secrets (for cloud deployment)
        if not val:
            try:
                val = st.secrets.get(env_key)
            except Exception:
                pass
                
        if val is not None:
            extracted_kwargs[kwarg_key] = val

    return Settings(**extracted_kwargs)
