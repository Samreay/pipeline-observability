from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service: str = Field(default="flows")
    push_gateway: str = Field(default="http://pushgateway:9091")


settings = Settings()
