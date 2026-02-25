from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: int = 0  # Allowed chat/group ID (negative for groups)
    telegram_webhook_url: str = ""  # Webhook URL (e.g., https://bot.example.com/telegram_webhook)
    telegram_webhook_path: str = "/telegram_webhook"  # Path for webhook endpoint
    
    # WireGuard
    wg_interface: str = "wg0"
    wg_config_path: str = "/etc/wireguard"
    wg_keys_path: str = "/etc/wireguard/keys"
    
    # External node SSH
    external_host: str = ""
    external_user: str = "root"
    external_ssh_key: str = "/root/.ssh/id_rsa"
    external_ssh_port: int = 22
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    api_secret: str = ""  # Optional API key for REST endpoints
    
    # WireGuard network settings for new users
    wg_network_prefix: str = "10.20.30"
    wg_next_ip_file: str = "/etc/wireguard/next_ip"
    wg_clients_dir: str = "/etc/wireguard/clients"
    wg_endpoint: str = ""  # Public endpoint for clients (IP or hostname)
    wg_endpoint_port: int = 17968
    wg_traffic_db: str = "/etc/wg-manager/traffic.db"
    
    class Config:
        env_file = "/etc/wg-manager/.env"
        env_prefix = "WG_MANAGER_"


settings = Settings()
