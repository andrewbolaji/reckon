"""Config loader — reads from env vars so the same code works locally and on AWS."""

import os
from dataclasses import dataclass


@dataclass
class WarehouseConfig:
    type: str  # "postgres" or "redshift"
    host: str
    port: int
    dbname: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> "WarehouseConfig":
        wtype = os.getenv("WAREHOUSE_TYPE", "postgres")
        prefix = "REDSHIFT" if wtype == "redshift" else "POSTGRES"
        return cls(
            type=wtype,
            host=os.environ[f"{prefix}_HOST"],
            port=int(os.environ[f"{prefix}_PORT"]),
            dbname=os.environ[f"{prefix}_DB"],
            user=os.environ[f"{prefix}_USER"],
            password=os.environ[f"{prefix}_PASSWORD"],
        )

    @property
    def connection_string(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.dbname}"
        )


@dataclass
class LakeConfig:
    type: str  # "local" or "s3"
    path: str | None = None
    bucket: str | None = None
    region: str | None = None

    @classmethod
    def from_env(cls) -> "LakeConfig":
        ltype = os.getenv("DATA_LAKE_TYPE", "local")
        if ltype == "s3":
            return cls(
                type="s3",
                bucket=os.environ["S3_BUCKET"],
                region=os.getenv("AWS_REGION", "us-east-1"),
            )
        return cls(type="local", path=os.getenv("DATA_LAKE_PATH", "/data/lake"))
