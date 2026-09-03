
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Razorpay
    razorpay_key_id: str = Field(..., env="RAZORPAY_KEY_ID")
    razorpay_key_secret: str = Field(..., env="RAZORPAY_KEY_SECRET")
    razorpay_base_url: str = Field(default="https://api.razorpay.com/v1", env="RAZORPAY_BASE_URL")
    # Optional fallback keys (test-mode payment_links cap is 30/day per account).
    # Format: comma-separated "key_id:key_secret" pairs, e.g. "rzp_test_x:secret1,rzp_test_y:secret2"
    razorpay_extra_keys: str = Field(default="", env="RAZORPAY_EXTRA_KEYS")
    # Webhook secret from the Razorpay dashboard (used to verify webhook HMAC).
    # If empty, webhooks are accepted but not verified (dev/ngrok only).
    webhook_secret: str = Field(default="", env="WEBHOOK_SECRET")

    @property
    def razorpay_creds_list(self) -> list[tuple[str, str]]:
        """Primary key first, then any fallback keys from RAZORPAY_EXTRA_KEYS."""
        creds = [(self.razorpay_key_id, self.razorpay_key_secret)]
        if self.razorpay_extra_keys:
            for pair in self.razorpay_extra_keys.split(","):
                pair = pair.strip()
                if not pair or ":" not in pair:
                    continue
                kid, _, secret = pair.partition(":")
                if kid and secret:
                    creds.append((kid.strip(), secret.strip()))
        return creds

    # Groq LLM (supports multiple keys for rotation)
    groq_api_keys: str = Field(..., env="GROQ_API_KEYS")  # Comma-separated
    groq_model: str = Field(default="qwen/qwen3.8-27b", env="GROQ_MODEL")

    @property
    def groq_key_list(self) -> list[str]:
        return [k.strip() for k in self.groq_api_keys.split(",") if k.strip()]

    # Laminar
    laminar_api_key: str = Field(default="", env="LMNR_PROJECT_API_KEY")
    laminar_project_id: str | None = Field(default=None, env="LAMINAR_PROJECT_ID")

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
    # Initial payment mode: "live" (real Razorpay API) or "simulate" (no API calls).
    # Can be flipped at runtime without a restart via chat or /payment-mode.
    payment_mode: str = Field(default="live", env="PAYMENT_MODE")

    # Policy engine (paise)
    monthly_budget_paise: int = Field(default=10_000_000, env="MONTHLY_BUDGET_PAISE")
    approval_threshold_paise: int = Field(default=5_000_000, env="APPROVAL_THRESHOLD_PAISE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
