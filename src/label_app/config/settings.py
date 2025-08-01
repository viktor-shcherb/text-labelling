from pydantic import BaseSettings

class Settings(BaseSettings):
    debug: bool = False
    admin_email: str = "admin@example.com"

settings = Settings()
