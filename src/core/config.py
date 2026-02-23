from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    env: str = os.getenv("ENV", "dev")


settings = Settings()