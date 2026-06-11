from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config= SettingsConfigDict(env_file =".env")
    anthropic_api_key: str
    github_token: str = ""

settings = Settings()