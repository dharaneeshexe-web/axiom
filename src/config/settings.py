from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # Razorpay
    razorpay_key_id: str = Field(..., env="RAZORPAY_KEY_ID")
    razorpay_key_secret: str = Field(..., env="RAZORPAY_KEY_SECRET")
    razorpay_base_url: str = Field(default="https://api.razorpay.com/v1", env="RAZORPAY_BASE_URL")

    # Groq LLM (supports multiple keys for rotation)
    groq_api_keys: str = Field(..., env="GROQ_API_KEYS")  # Comma-separated
    groq_model: str = Field(default="qwen/qwen3.8-27b", env="GROQ_MODEL")

    @property
    def groq_key_list(self) -> list[str]:
        return [k.strip() for k in self.groq_api_keys.split(",") if k.strip()]

    # Laminar
    laminar_api_key: str = Field(default="", env="LMNR_PROJECT_API_KEY")
    laminar_project_id: Optional[str] = Field(default=None, env="LAMINAR_PROJECT_ID")

    # Database
    database_url: str = Field(default="sqlite:///./payments.db", env="DATABASE_URL")

    # App
    app_host: str = Field(default="0.0.0.0", env="APP_HOST")
    app_port: int = Field(default=8000, env="APP_PORT")
    debug: bool = Field(default=False, env="DEBUG")

    # Agent
    max_retries: int = Field(default=2, env="MAX_RETRIES")
    payment_timeout: int = Field(default=30, env="PAYMENT_TIMEOUT")
    max_llm_iterations: int = Field(default=10, env="MAX_LLM_ITERATIONS")
    demo_failure: str = Field(default="none", env="DEMO_FAILURE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
