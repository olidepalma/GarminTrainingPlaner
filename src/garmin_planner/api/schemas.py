"""Contratos de las peticiones HTTP."""

from pydantic import BaseModel, Field, SecretStr


class PasswordBody(BaseModel):
    password: SecretStr


class GarminBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr


class MFABody(BaseModel):
    code: str = Field(min_length=4, max_length=12, pattern=r"^[0-9]+$")


class ModelBody(BaseModel):
    model: str = Field(min_length=1, max_length=100)


class OptionsBody(BaseModel):
    sleep: bool = False
    hrv: bool = False


class CoachWorkoutBody(BaseModel):
    source: str = Field(pattern=r"^[0-9a-f]{64}$")


class SendWorkoutBody(BaseModel):
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class EnabledBody(BaseModel):
    enabled: bool


class ProStartBody(BaseModel):
    new_account: bool = False
