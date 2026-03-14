from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Asterisk / SIP
    asterisk_host: str = "127.0.0.1"
    asterisk_port: int = 5060
    sip_username: str = "sipinator"
    sip_password: str = ""
    sip_local_port: int = 5080
    sip_extension: str = "9000"

    # APNs
    apns_key_path: str = "/certs/AuthKey.p8"
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_bundle_id: str = ""
    apns_use_sandbox: bool = True

    # Database
    database_path: str = "/data/sipinator.db"

    # Security
    api_secret_key: str = "changeme"

    # Logging
    log_level: str = "INFO"

    @property
    def apns_topic(self) -> str:
        return f"{self.apns_bundle_id}.voip"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
