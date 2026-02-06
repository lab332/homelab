import subprocess
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple
import paramiko

from config import settings


@dataclass
class CommandResult:
    success: bool
    output: str
    error: str = ""


def run_local_command(command: str) -> CommandResult:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        return CommandResult(
            success=result.returncode == 0,
            output=result.stdout.strip(),
            error=result.stderr.strip()
        )
    except subprocess.TimeoutExpired:
        return CommandResult(success=False, output="", error="Command timed out")
    except Exception as e:
        return CommandResult(success=False, output="", error=str(e))


def run_remote_command(command: str) -> CommandResult:
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        ssh.connect(
            hostname=settings.external_host,
            port=settings.external_ssh_port,
            username=settings.external_user,
            key_filename=settings.external_ssh_key,
            timeout=10
        )
        
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        exit_code = stdout.channel.recv_exit_status()
        
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        
        ssh.close()
        
        return CommandResult(
            success=exit_code == 0,
            output=output,
            error=error
        )
    except Exception as e:
        return CommandResult(success=False, output="", error=str(e))


def restart_internal() -> CommandResult:
    cmd = f"wg-quick down {settings.wg_interface} ; wg-quick up {settings.wg_interface}"
    return run_local_command(cmd)


def restart_external() -> CommandResult:
    cmd = f"wg-quick down {settings.wg_interface} ; wg-quick up {settings.wg_interface}"
    return run_remote_command(cmd)


def restart_all() -> Tuple[CommandResult, CommandResult]:
    internal_result = restart_internal()
    external_result = restart_external()
    return internal_result, external_result


def get_status_internal() -> CommandResult:
    return run_local_command("wg show")


def get_status_external() -> CommandResult:
    return run_remote_command("wg show")


def generate_keypair() -> Tuple[str, str]:
    private_key_result = run_local_command("wg genkey")
    if not private_key_result.success:
        raise Exception(f"Failed to generate private key: {private_key_result.error}")
    
    private_key = private_key_result.output
    
    public_key_result = run_local_command(f"echo '{private_key}' | wg pubkey")
    if not public_key_result.success:
        raise Exception(f"Failed to generate public key: {public_key_result.error}")
    
    public_key = public_key_result.output
    
    return private_key, public_key


def get_next_ip() -> int:
    ip_file = Path(settings.wg_next_ip_file)
    
    if ip_file.exists():
        current = int(ip_file.read_text().strip())
    else:
        current = 10  # Start from .10 (1 is internal, 2 is external)
    
    next_ip = current + 1
    ip_file.write_text(str(next_ip))
    
    return current


def create_user(username: str) -> dict:
    private_key, public_key = generate_keypair()

    ip_num = get_next_ip()
    client_ip = f"{settings.wg_network_prefix}.{ip_num}"

    clients_dir = Path(settings.wg_clients_dir)
    clients_dir.mkdir(parents=True, exist_ok=True)
    
    client_dir = clients_dir / username
    client_dir.mkdir(exist_ok=True)

    (client_dir / "privatekey").write_text(private_key)
    (client_dir / "publickey").write_text(public_key)

    server_pubkey_result = run_local_command(f"cat {settings.wg_keys_path}/publickey")
    if not server_pubkey_result.success:
        raise Exception(f"Failed to read server public key: {server_pubkey_result.error}")
    
    server_public_key = server_pubkey_result.output

    if settings.wg_endpoint:
        endpoint = settings.wg_endpoint
    else:
        # Fallback: detect public IP (force IPv4)
        endpoint_result = run_local_command("curl -4 -s ifconfig.me")
        endpoint = endpoint_result.output if endpoint_result.success else "CONFIGURE_ME"
    
    endpoint_port = settings.wg_endpoint_port

    client_config = f"""[Interface]
PrivateKey = {private_key}
Address = {client_ip}/32
DNS = 1.1.1.1, 8.8.8.8

[Peer]
PublicKey = {server_public_key}
AllowedIPs = 0.0.0.0/0
Endpoint = {endpoint}:{endpoint_port}
PersistentKeepalive = 25
"""
    
    config_path = client_dir / f"{username}.conf"
    config_path.write_text(client_config)

    peer_config = f"""
# Client: {username}
[Peer]
PublicKey = {public_key}
AllowedIPs = {client_ip}/32
"""

    server_config_path = Path(settings.wg_config_path) / f"{settings.wg_interface}.conf"
    with open(server_config_path, "a") as f:
        f.write(peer_config)

    qr_path = client_dir / f"{username}.png"
    run_local_command(f"cat {config_path} | qrencode -t png -o {qr_path}")

    run_local_command(f"bash -c 'wg syncconf {settings.wg_interface} <(wg-quick strip {settings.wg_interface})'")
    
    return {
        "username": username,
        "ip": client_ip,
        "config_path": str(config_path),
        "qr_path": str(qr_path),
        "public_key": public_key
    }


def list_users() -> list:
    clients_dir = Path(settings.wg_clients_dir)
    if not clients_dir.exists():
        return []
    
    users = []
    for client_dir in clients_dir.iterdir():
        if client_dir.is_dir():
            users.append(client_dir.name)
    
    return users


def delete_user(username: str) -> dict:
    import re
    import shutil
    
    clients_dir = Path(settings.wg_clients_dir)
    client_dir = clients_dir / username
    
    if not client_dir.exists():
        raise Exception(f"User {username} not found")

    pubkey_file = client_dir / "publickey"
    if pubkey_file.exists():
        public_key = pubkey_file.read_text().strip()

        server_config_path = Path(settings.wg_config_path) / f"{settings.wg_interface}.conf"
        if server_config_path.exists():
            config_content = server_config_path.read_text()

            pattern = rf'\n# Client: {re.escape(username)}\n\[Peer\]\nPublicKey = {re.escape(public_key)}\nAllowedIPs = [^\n]+\n?'
            new_content = re.sub(pattern, '', config_content)
            
            server_config_path.write_text(new_content)

    shutil.rmtree(client_dir)

    run_local_command(f"bash -c 'wg syncconf {settings.wg_interface} <(wg-quick strip {settings.wg_interface})'")
    
    return {
        "username": username,
        "deleted": True
    }
