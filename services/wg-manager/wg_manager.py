import subprocess
import os
import sqlite3
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple, List
import paramiko

from config import settings

logger = logging.getLogger(__name__)


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
    snapshot_traffic()
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


@dataclass
class PeerTraffic:
    username: str
    public_key: str
    allowed_ips: str
    latest_handshake: int
    rx_bytes: int
    tx_bytes: int
    endpoint: str


def _get_db() -> sqlite3.Connection:
    db_path = Path(settings.wg_traffic_db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS traffic_cumulative (
            public_key   TEXT PRIMARY KEY,
            baseline_rx  INTEGER DEFAULT 0,
            baseline_tx  INTEGER DEFAULT 0,
            last_seen_rx INTEGER DEFAULT 0,
            last_seen_tx INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS traffic_daily (
            public_key TEXT,
            date       TEXT,
            rx_bytes   INTEGER DEFAULT 0,
            tx_bytes   INTEGER DEFAULT 0,
            PRIMARY KEY (public_key, date)
        )
    """)
    conn.commit()
    return conn


def snapshot_traffic() -> Optional[str]:
    result = run_local_command(f"wg show {settings.wg_interface} dump")
    if not result.success:
        logger.debug(f"snapshot_traffic: wg show failed: {result.error}")
        return None

    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = _get_db()
    try:
        lines = result.output.strip().split("\n")
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) < 8:
                continue

            pubkey = parts[0]
            current_rx = int(parts[5])
            current_tx = int(parts[6])

            row = conn.execute(
                "SELECT baseline_rx, baseline_tx, last_seen_rx, last_seen_tx "
                "FROM traffic_cumulative WHERE public_key = ?",
                (pubkey,),
            ).fetchone()

            if row is None:
                baseline_rx, baseline_tx, last_seen_rx, last_seen_tx = 0, 0, 0, 0
            else:
                baseline_rx, baseline_tx, last_seen_rx, last_seen_tx = row

            if current_rx < last_seen_rx:
                baseline_rx += last_seen_rx
            if current_tx < last_seen_tx:
                baseline_tx += last_seen_tx

            conn.execute(
                "INSERT OR REPLACE INTO traffic_cumulative "
                "(public_key, baseline_rx, baseline_tx, last_seen_rx, last_seen_tx) "
                "VALUES (?, ?, ?, ?, ?)",
                (pubkey, baseline_rx, baseline_tx, current_rx, current_tx),
            )

            total_rx = baseline_rx + current_rx
            total_tx = baseline_tx + current_tx
            conn.execute(
                "INSERT INTO traffic_daily (public_key, date, rx_bytes, tx_bytes) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(public_key, date) DO UPDATE SET rx_bytes=?, tx_bytes=?",
                (pubkey, today, total_rx, total_tx, total_rx, total_tx),
            )

        conn.commit()
    finally:
        conn.close()

    return result.output


def _format_bytes(b: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if b < 1024:
            return f"{b:.2f} {unit}" if unit != "B" else f"{b} {unit}"
        b /= 1024
    return f"{b:.2f} PiB"


def _format_handshake(ts: int) -> str:
    if ts == 0:
        return "never"
    delta = int(time.time()) - ts
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m {delta % 60}s ago"
    if delta < 86400:
        h = delta // 3600
        m = (delta % 3600) // 60
        return f"{h}h {m}m ago"
    d = delta // 86400
    h = (delta % 86400) // 3600
    return f"{d}d {h}h ago"


def _get_peer_to_user_map() -> dict:
    clients_dir = Path(settings.wg_clients_dir)
    if not clients_dir.exists():
        return {}

    mapping = {}
    for client_dir in clients_dir.iterdir():
        if not client_dir.is_dir():
            continue
        pubkey_file = client_dir / "publickey"
        if pubkey_file.exists():
            pubkey = pubkey_file.read_text().strip()
            mapping[pubkey] = client_dir.name
    return mapping


def _parse_wg_dump(dump_output: str, peer_map: dict) -> list:
    lines = dump_output.strip().split("\n")
    if len(lines) < 2:
        return []

    peers = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        pubkey = parts[0]
        username = peer_map.get(pubkey, pubkey[:16] + "...")
        peers.append(PeerTraffic(
            username=username,
            public_key=pubkey,
            endpoint=parts[2] if parts[2] != "(none)" else "",
            allowed_ips=parts[3],
            latest_handshake=int(parts[4]),
            rx_bytes=int(parts[5]),
            tx_bytes=int(parts[6]),
        ))
    return peers


def get_traffic_stats() -> dict:
    peer_map = _get_peer_to_user_map()
    dump_output = snapshot_traffic()

    if dump_output is None:
        return {"success": False, "error": "Failed to read WG counters", "peers": []}

    peers = _parse_wg_dump(dump_output, peer_map)

    conn = _get_db()
    try:
        for p in peers:
            row = conn.execute(
                "SELECT baseline_rx, baseline_tx FROM traffic_cumulative "
                "WHERE public_key = ?",
                (p.public_key,),
            ).fetchone()
            if row:
                p.rx_bytes += row[0]
                p.tx_bytes += row[1]
    finally:
        conn.close()

    peers.sort(key=lambda p: p.rx_bytes + p.tx_bytes, reverse=True)
    return {"success": True, "error": "", "peers": peers}


def get_traffic_history(days: int = 7) -> List[dict]:
    peer_map = _get_peer_to_user_map()
    since = (datetime.utcnow() - timedelta(days=days + 1)).strftime("%Y-%m-%d")

    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT public_key, date, rx_bytes, tx_bytes "
            "FROM traffic_daily WHERE date >= ? ORDER BY date",
            (since,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    snapshots: dict[str, dict[str, tuple]] = {}
    for pubkey, date, rx, tx in rows:
        snapshots.setdefault(pubkey, {})[date] = (rx, tx)

    all_dates = sorted({r[1] for r in rows})
    result = []
    for i, date in enumerate(all_dates):
        if i == 0:
            continue
        prev_date = all_dates[i - 1]
        day_peers = []
        for pubkey, date_map in snapshots.items():
            if date not in date_map:
                continue
            cur_rx, cur_tx = date_map[date]
            prev_rx, prev_tx = date_map.get(prev_date, (0, 0))
            delta_rx = max(cur_rx - prev_rx, 0)
            delta_tx = max(cur_tx - prev_tx, 0)
            if delta_rx == 0 and delta_tx == 0:
                continue
            username = peer_map.get(pubkey, pubkey[:16] + "...")
            day_peers.append({"username": username, "rx": delta_rx, "tx": delta_tx})
        day_peers.sort(key=lambda p: p["rx"] + p["tx"], reverse=True)
        result.append({"date": date, "peers": day_peers})

    return result[-days:]


def format_traffic_history(history: List[dict]) -> str:
    if not history:
        return ""

    lines = ["\n📅 *Last 7 days*\n"]
    for day in history:
        try:
            dt = datetime.strptime(day["date"], "%Y-%m-%d")
            label = dt.strftime("%a %d %b")
        except ValueError:
            label = day["date"]

        if not day["peers"]:
            lines.append(f"`{label}`:  --")
            continue

        parts = []
        for p in day["peers"]:
            total = _format_bytes(p["rx"] + p["tx"])
            parts.append(f"{p['username']} `{total}`")
        lines.append(f"`{label}`:  {' | '.join(parts)}")

    return "\n".join(lines)


def format_traffic_report(stats: dict) -> str:
    if not stats["success"]:
        return f"❌ Failed to get traffic stats: {stats['error']}"

    peers = stats["peers"]
    if not peers:
        return "📊 No peers found"

    total_rx = sum(p.rx_bytes for p in peers)
    total_tx = sum(p.tx_bytes for p in peers)

    lines = ["📊 *WireGuard Traffic*\n"]
    for p in peers:
        total = p.rx_bytes + p.tx_bytes
        status = "🟢" if p.latest_handshake != 0 and (
            time.time() - p.latest_handshake < 180
        ) else "⚪"
        lines.append(f"{status} *{p.username}*")
        lines.append(f"    ↓ `{_format_bytes(p.rx_bytes)}` ↑ `{_format_bytes(p.tx_bytes)}`  Σ `{_format_bytes(total)}`")
        lines.append(f"    🤝 {_format_handshake(p.latest_handshake)}")
        if p.endpoint:
            lines.append(f"    🌐 `{p.endpoint}`")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"*Total:*  ↓ `{_format_bytes(total_rx)}` ↑ `{_format_bytes(total_tx)}`  Σ `{_format_bytes(total_rx + total_tx)}`")

    return "\n".join(lines)


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
