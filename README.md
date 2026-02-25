# Homelab Infrastructure

Ansible-конфигурация для развёртывания VPN-инфраструктуры с мониторингом и Telegram-ботом.

## Компоненты

| Компонент | Playbook | Описание |
|-----------|----------|----------|
| **VPN** | `vpn.yml` | WireGuard туннель между двумя нодами |
| **WG Manager** | `wg-manager.yml` | Telegram-бот для управления VPN клиентами |
| **Monitoring** | `monitoring.yml` | Prometheus + Alertmanager с алертами в Telegram |

## Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         INTERNET                                │
└─────────────────────────────────────────────────────────────────┘
                    │                           │
                    ▼                           ▼
┌─────────────────────────────┐   ┌─────────────────────────────┐
│      vpn-internal           │   │       vpn-external          │
│      (Локальный)            │   │      (Зарубежный)           │
│                             │   │                             │
│  ┌─────────────────────┐    │   │   ┌─────────────────────┐   │
│  │ WireGuard (wg0)     │◄───┼───┼──►│ WireGuard (wg0)     │   │
│  │ 10.20.30.1          │    │   │   │ 10.20.30.2          │   │
│  └─────────────────────┘    │   │   └─────────────────────┘   │
│                             │   │                             │
│  ┌─────────────────────┐    │   │   ┌─────────────────────┐   │
│  │ Node Exporter :9100 │    │   │   │ Node Exporter :9100 │   │
│  │ WG Exporter   :9586 │    │   │   │ WG Exporter   :9586 │   │
│  └─────────────────────┘    │   │   └─────────────────────┘   │
│                             │   │                             │
│  ┌─────────────────────┐    │   │                             │
│  │ WG Manager Bot      │    │   │                             │
│  │ (Docker, Telegram)  │    │   │                             │
│  └─────────────────────┘    │   │                             │
│                             │   │                             │
│  ┌─────────────────────┐    │   │                             │
│  │ Prometheus    :9090 │────┼───┼───► scrapes both hosts      │
│  │ Alertmanager  :9093 │────┼───┼───► sends alerts to TG      │
│  │ Nginx (SSL)   :443  │    │   │                             │
│  └─────────────────────┘    │   │                             │
└─────────────────────────────┘   └─────────────────────────────┘
```

## Требования

### Серверы

- 2 сервера с Ubuntu 22.04+ (внутренний и внешний)
- SSH доступ с ключами
- Открытые порты:
  - **vpn-internal**: 17968/UDP (WireGuard), 80/443 (Nginx), 9090 (Prometheus), 9093 (Alertmanager), 9100 (Node Exporter), 9586 (WG Exporter)
  - **vpn-external**: 51820/UDP (WireGuard), 9100 (Node Exporter), 9586 (WG Exporter)

### Локальная машина

- Python 3.9+
- Ansible 2.15+

## Необходимые креды

### 1. Telegram Bot Token

Для WG Manager бота и алертов мониторинга.

**Как получить:**
1. Открой [@BotFather](https://t.me/BotFather) в Telegram
2. Отправь `/newbot`
3. Следуй инструкциям, придумай имя бота
4. Скопируй токен вида `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

### 2. Telegram Chat ID

ID чата/группы для алертов и управления ботом.

**Как получить:**
1. Создай приватную группу в Telegram
2. Добавь туда своего бота
3. Отправь любое сообщение в группу
4. Открой `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Найди `"chat":{"id":-100XXXXXXXXXX}` — это твой Chat ID

> ⚠️ Для групп Chat ID отрицательный и начинается с `-100`

### 3. Telegram Topics (Thread ID) — опционально

Если используешь **Topics (Темы)** в группе для разделения алертов и управления ботом.

**Как получить Thread ID:**
1. Включи "Темы" в настройках группы (Settings → Topics)
2. Создай нужные топики (например, "🔥 Alerts" и "🔐 WireGuard")
3. Открой топик в **Telegram Web**: `https://web.telegram.org/a/#-100XXXXXXXXXX_<NUMBER>`
4. Число после `_` в URL — это `thread_id` (например, `_97` → thread_id = `97`)

**Настройка в `hosts.yml`:**
```yaml
wg_manager_telegram_alerts_thread_id: 97   # ID топика для алертов
wg_manager_telegram_bot_thread_id: 99      # ID топика для бота (не используется, бот отвечает автоматически)
```

> 💡 Если не используешь Topics, оставь значения `0` — сообщения будут идти в General.

### 4. Cloudflare API Token (опционально)

Для автоматического выпуска SSL сертификатов через Let's Encrypt DNS challenge.

**Как получить:**
1. Зайди на [Cloudflare Dashboard](https://dash.cloudflare.com/profile/api-tokens)
2. Нажми "Create Token"
3. Используй шаблон "Edit zone DNS"
4. Выбери нужный домен в Zone Resources
5. Скопируй токен

**Требуется только если:**
- Используешь `wg-manager` с webhook (HTTPS)
- Хочешь автоматический SSL для домена

## Быстрый старт

### 1. Клонирование репозитория

```bash
git clone https://github.com/yourrepo/homelab.git
cd homelab/ansible
```

### 2. Установка зависимостей

```bash
# Создание виртуального окружения
python3 -m venv .venv
source .venv/bin/activate

# Установка Ansible
pip install ansible

# Установка Ansible коллекций и ролей
ansible-galaxy install -r requirements.yml
```

### 3. Настройка инвентаря

Скопируй пример и отредактируй:

```bash
cp inventory/hosts.yml.example inventory/hosts.yml
```

Заполни свои данные:

```yaml
---
all:
  children:
    vpn:
      hosts:
        vpn-internal:
          ansible_host: YOUR_INTERNAL_IP      # IP внутреннего сервера
          wg_role: internal
          wg_address: "10.20.30.1/32"
          wg_listen_port: 17968
          wg_endpoint: "YOUR_INTERNAL_IP"
          wg_endpoint_port: 17968
          # WG Manager
          wg_manager_enabled: true
          wg_manager_external_host: "YOUR_EXTERNAL_IP"
          wg_manager_external_ssh_key: "/root/.ssh/id_ed25519"
          wg_manager_wg_endpoint: "YOUR_INTERNAL_IP"
          wg_manager_wg_endpoint_port: 17968

        vpn-external:
          ansible_host: YOUR_EXTERNAL_IP      # IP внешнего сервера
          wg_role: external
          wg_address: "10.20.30.2/32"
          wg_listen_port: 51820
          wg_manager_enabled: false

  vars:
    # === ОБЯЗАТЕЛЬНЫЕ ===
    # Telegram Bot (см. раздел "Необходимые креды")
    wg_manager_telegram_bot_token: "YOUR_BOT_TOKEN"
    wg_manager_telegram_chat_id: YOUR_CHAT_ID  # число, для групп отрицательное

    # === ОПЦИОНАЛЬНЫЕ (Telegram Topics) ===
    # Если используешь Topics в группе, укажи thread_id для алертов
    # wg_manager_telegram_alerts_thread_id: 97   # ID топика для алертов (0 = General)
    # wg_manager_telegram_bot_thread_id: 99      # ID топика для бота (0 = General, бот отвечает автоматически)

    # === ОПЦИОНАЛЬНЫЕ (для SSL/Webhook) ===
    # Cloudflare (для автоматического SSL)
    nginx_ssl_cloudflare_token: "YOUR_CLOUDFLARE_TOKEN"
    nginx_ssl_domain: "yourdomain.com"
    nginx_ssl_email: "admin@yourdomain.com"

    # Webhook (рекомендуется для production)
    wg_manager_telegram_webhook_url: "https://yourdomain.com"
    wg_manager_telegram_webhook_path: "/telegram_webhook"
```

### 4. Проверка подключения

```bash
ansible all -m ping
```

### 5. Деплой

```bash
# Шаг 1: VPN (обязательно первым)
ansible-playbook playbooks/vpn.yml

# Шаг 2: WG Manager (опционально)
ansible-playbook playbooks/wg-manager.yml

# Шаг 3: Мониторинг (опционально)
ansible-playbook playbooks/monitoring.yml
```

## Зависимости между playbook'ами

```
vpn.yml (базовый)
    │
    ├──► wg-manager.yml (требует vpn.yml)
    │
    └──► monitoring.yml (независимый, но использует те же хосты)
            │
            └──► nginx_ssl (требуется для webhook wg-manager)
```

### Что можно деплоить отдельно

| Playbook | Зависимости | Можно запускать отдельно? |
|----------|-------------|---------------------------|
| `vpn.yml` | Нет | ✅ Да |
| `wg-manager.yml` | `vpn.yml`, Docker | ⚠️ Требует WireGuard и Docker |
| `monitoring.yml` | Docker на хостах | ✅ Да (Docker ставится автоматически) |
| `monitoring.yml --tags nginx_ssl` | Домен в Cloudflare | ✅ Да |

### Безопасный порядок деплоя

```bash
# Только VPN (минимальная установка)
ansible-playbook playbooks/vpn.yml

# Добавить мониторинг (можно позже)
ansible-playbook playbooks/monitoring.yml

# Добавить бота (можно позже, требует VPN)
ansible-playbook playbooks/wg-manager.yml

# Добавить SSL для webhook (можно позже)
ansible-playbook playbooks/monitoring.yml --tags nginx_ssl
```

## Структура проекта

```
services/
└── wg-manager/
    ├── Dockerfile             # Образ: python:3.12-slim + wireguard-tools, iptables, nftables, qrencode
    ├── docker-compose.yml     # Запуск: privileged, host network, volumes
    ├── .dockerignore
    ├── app.py                 # FastAPI приложение + webhook
    ├── telegram_bot.py        # Telegram бот (команды, меню, scheduled jobs)
    ├── wg_manager.py          # Логика: управление WG, трафик, пользователи
    ├── config.py              # Pydantic Settings из /etc/wg-manager/.env
    ├── requirements.txt       # Python-зависимости
    └── env.example            # Пример .env

ansible/
├── ansible.cfg                 # Конфигурация Ansible
├── requirements.yml            # Зависимости (Galaxy)
├── inventory/
│   ├── hosts.yml              # Инвентарь (ТВОИ ДАННЫЕ)
│   ├── hosts.yml.example      # Пример инвентаря
│   └── group_vars/
│       └── vpn.yml            # Переменные для группы vpn
├── playbooks/
│   ├── vpn.yml                # WireGuard VPN
│   ├── wg-manager.yml         # Telegram бот (Docker)
│   └── monitoring.yml         # Prometheus + Alertmanager
└── roles/
    ├── wireguard/             # Роль WireGuard
    ├── wg-manager/            # Роль Telegram бота (Docker deployment)
    │   ├── tasks/main.yml     # Копирует файлы, собирает образ, запускает контейнер
    │   ├── templates/
    │   │   ├── docker-compose.yml.j2
    │   │   └── env.j2
    │   ├── handlers/main.yml  # Rebuild / Restart через docker compose
    │   └── defaults/main.yml
    ├── wireguard_exporter/    # Экспортер метрик WG
    └── nginx_ssl/             # Nginx + Let's Encrypt
```

## Компоненты детально

### VPN (vpn.yml)

WireGuard туннель между internal и external нодами.

**Что делает:**
- Устанавливает WireGuard
- Генерирует ключи
- Настраивает маршрутизацию
- Весь трафик идёт через external ноду

**Проверка:**
```bash
# На любой ноде
wg show
ping 10.20.30.1  # internal
ping 10.20.30.2  # external
```

### WG Manager (wg-manager.yml)

Telegram бот для управления VPN клиентами. Работает в Docker-контейнере на internal ноде.

**Функции:**
- `/start` — главное меню
- Создание/удаление клиентов
- QR-коды для мобильных
- Перезапуск туннелей (internal — `wg-quick down/up` из контейнера, external — по SSH)
- Статус подключений
- Мониторинг трафика с лимитами и автоблокировкой

**Docker:**
- Образ собирается локально из `services/wg-manager/Dockerfile`
- Контейнер работает с `privileged: true` и `network_mode: host` — нужно для управления WireGuard интерфейсом на хосте
- Volumes: `/etc/wireguard`, `/etc/wg-manager`, `/run/wireguard`, SSH-ключ для внешней ноды

**Режимы Telegram:**
- **Polling** (по умолчанию) — бот сам опрашивает Telegram
- **Webhook** (рекомендуется) — Telegram отправляет обновления на HTTPS endpoint

### Monitoring (monitoring.yml)

Полный стек мониторинга.

**Компоненты:**

| Сервис | Порт | Описание |
|--------|------|----------|
| Node Exporter | 9100 | Метрики системы (CPU, RAM, диск) |
| WG Exporter | 9586 | Метрики WireGuard |
| Prometheus | 9090 | Сбор и хранение метрик |
| Alertmanager | 9093 | Отправка алертов в Telegram |

**Алерты:**

| Алерт | Severity | Триггер |
|-------|----------|---------|
| InstanceDown | critical | Хост недоступен > 2 мин |
| HighCpuUsage | warning | CPU > 80% > 5 мин |
| HighMemoryUsage | warning | RAM > 85% > 5 мин |
| DiskSpaceLow | warning | Диск < 15% |
| DiskSpaceCritical | critical | Диск < 5% |
| WireGuardPeerDown | warning | Peer без handshake > 3 мин |
| WireGuardInterfaceDown | critical | WG интерфейс упал |
| ServiceDown | critical | Systemd сервис упал |

## Обновление

```bash
# Обновить WG Manager (пересобирает Docker-образ и перезапускает контейнер)
ansible-playbook playbooks/wg-manager.yml

# Или вручную на сервере
ssh root@YOUR_IP 'cd /opt/wg-manager && docker compose up -d --build'

# Обновить только мониторинг
ansible-playbook playbooks/monitoring.yml

# Обновить только SSL сертификат
ansible-playbook playbooks/monitoring.yml --tags nginx_ssl
```

## Troubleshooting

### VPN не работает

```bash
# Проверить статус WireGuard
ssh root@YOUR_IP 'wg show'

# Логи
ssh root@YOUR_IP 'journalctl -u wg-quick@wg0 -f'

# Перезапуск
ssh root@YOUR_IP 'systemctl restart wg-quick@wg0'
```

### Бот не отвечает

```bash
# Статус контейнера
ssh root@YOUR_IP 'docker ps -f name=wg-manager'

# Логи
ssh root@YOUR_IP 'docker logs --tail 50 -f wg-manager'

# Перезапуск
ssh root@YOUR_IP 'cd /opt/wg-manager && docker compose restart'

# Пересборка (после изменения кода)
ssh root@YOUR_IP 'cd /opt/wg-manager && docker compose up -d --build'

# Проверить .env
ssh root@YOUR_IP 'cat /etc/wg-manager/.env'
```

### Алерты не приходят

```bash
# Проверить Alertmanager
curl http://YOUR_IP:9093/api/v2/status

# Отправить тестовый алерт
curl -X POST http://YOUR_IP:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{"labels":{"alertname":"TestAlert","severity":"warning"}}]'
```

### SSL не работает

```bash
# Проверить сертификат
ssh root@YOUR_IP 'ls -la /etc/letsencrypt/live/'

# Проверить Nginx
ssh root@YOUR_IP 'nginx -t && systemctl status nginx'

# Логи Certbot
ssh root@YOUR_IP 'cat /var/log/letsencrypt/letsencrypt.log'
```

## Безопасность

⚠️ **Не коммитьте `inventory/hosts.yml` с реальными данными!**

Файл уже добавлен в `.gitignore`. Используйте `hosts.yml.example` как шаблон.

### Чувствительные данные

| Переменная | Описание | Где хранить |
|------------|----------|-------------|
| `wg_manager_telegram_bot_token` | Токен бота | inventory/hosts.yml |
| `wg_manager_telegram_chat_id` | ID чата | inventory/hosts.yml |
| `wg_manager_telegram_alerts_thread_id` | ID топика для алертов (0 = General) | inventory/hosts.yml |
| `wg_manager_telegram_bot_thread_id` | ID топика для бота (0 = General) | inventory/hosts.yml |
| `nginx_ssl_cloudflare_token` | API токен CF | inventory/hosts.yml |

