from pydantic import BaseSettings

class Settings(BaseSettings):
    debug: bool = False

settings = Settings()
