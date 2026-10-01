"""Configuración compartida por CLI y servidor, sin credenciales incorporadas."""

from ipaddress import IPv4Address, ip_address
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GTP_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Desarrollo con login privado; la publicación remota necesita HTTPS y configuración propia.
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    public_origin: str | None = None
    trusted_proxy_ips: str = "127.0.0.1,::1"

    @field_validator("host")
    @classmethod
    def valid_bind_address(cls, value):
        if value in ("127.0.0.1", "::1", "0.0.0.0"):
            return value
        try:
            address = ip_address(value)
        except ValueError as exc:
            raise ValueError("Indica loopback o una IP local privada") from exc
        if not isinstance(address, IPv4Address) or not address.is_private or address.is_unspecified:
            raise ValueError("La escucha debe usar loopback o una IP local privada")
        return value

    @field_validator("public_origin")
    @classmethod
    def valid_origin(cls, value):
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Indica una URL HTTPS sin ruta, credenciales ni parámetros")
        return value.rstrip("/")

    @model_validator(mode="after")
    def network_requires_domain(self):
        if self.host not in ("127.0.0.1", "::1") and not self.public_origin:
            raise ValueError("La escucha de red requiere GTP_PUBLIC_ORIGIN con HTTPS")
        if "*" in self.trusted_proxy_ips:
            raise ValueError("Indica IPs concretas del proxy; no se admite confiar en todos")
        return self

    timezone: str = "Europe/Madrid"
    coach_provider: Literal["chatgpt_pro"] = "chatgpt_pro"
    data_dir: Path = Path("data")
    initial_days: int = Field(default=90, ge=7, le=365)
    sync_hour: int = Field(default=3, ge=0, le=23)
    auto_sync: bool = True

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Usa una zona IANA válida, como Europe/Madrid") from exc
        return value
