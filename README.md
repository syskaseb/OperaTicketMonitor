# Opera Ticket Monitor 🎭

Monitor dostępności biletów na **Halkę** i **Straszny Dwór** we wszystkich głównych operach w Polsce.

## Funkcje

- 🔍 Automatyczne przeszukiwanie 9 polskich oper co 15 minut
- 📧 Powiadomienia email gdy bilety się pojawią
- ☁️ Gotowy do deploymentu na AWS (Lambda lub ECS)
- 💾 Pamięta o czym już powiadomił (bez spamu!)

## Monitorowane teatry

| Opera | Miasto |
|-------|--------|
| Teatr Wielki - Opera Narodowa | Warszawa |
| Opera Krakowska | Kraków |
| Opera Wrocławska | Wrocław |
| Opera Bałtycka | Gdańsk |
| Opera Śląska | Bytom |
| Opera Nova | Bydgoszcz |
| Teatr Wielki | Łódź |
| Teatr Wielki im. Moniuszki | Poznań |
| Opera i Filharmonia Podlaska | Białystok |

## Szybki start (lokalnie)

### 1. Instalacja

```bash
# Klonuj repo
cd PythonProject

# Stwórz venv (Python 3.12+)
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# lub .venv\Scripts\activate  # Windows

# Zainstaluj zależności
pip install -r requirements.txt
```

### 2. Konfiguracja email

Aby otrzymywać powiadomienia, potrzebujesz:

1. **Konto Gmail** do wysyłania emaili
2. **App Password** (nie zwykłe hasło!) - [jak utworzyć](https://support.google.com/accounts/answer/185833)

```bash
# Ustaw zmienne środowiskowe
export SENDER_EMAIL="twoj-email@gmail.com"
export SENDER_PASSWORD="xxxx-xxxx-xxxx-xxxx"  # App Password!
```

### 3. Uruchomienie

```bash
# Uruchom monitor (działa ciągle)
python monitor.py

# Lub pojedyncze sprawdzenie (do testów)
python -c "from monitor import OperaTicketMonitor; import asyncio; m = OperaTicketMonitor(); asyncio.run(m.run_once())"
```

## Deploy na AWS

### Opcja 1: AWS Lambda (zalecane) 💰

Najtańsza opcja - płacisz tylko za wykonania (~$0.50/miesiąc).

```bash
# Zainstaluj SAM CLI
pip install aws-sam-cli

# Deploy
cd aws
sam build
sam deploy --guided
```

Podczas guided deploy podaj:
- `SenderEmail` - twój Gmail
- `SenderPassword` - App Password

### Opcja 2: Docker (ECS/Fargate)

```bash
# Build
docker build -t opera-monitor .

# Run lokalnie
docker run -e SENDER_EMAIL=xxx -e SENDER_PASSWORD=xxx opera-monitor

# Push do ECR i deploy na ECS/Fargate
```

### Opcja 3: EC2

```bash
# Na EC2 (Amazon Linux 2023)
sudo yum install python3.12
pip install -r requirements.txt

# Uruchom w tle z nohup lub systemd
nohup python monitor.py &
```

## Konfiguracja

Edytuj `config.py` aby zmienić:

- **Częstotliwość sprawdzania** - domyślnie 15 minut
- **Email odbiorcy** - domyślnie syskaseb@gmail.com
- **Włącz/wyłącz konkretne opery**
- **Dodaj więcej oper do szukania**

```python
# config.py
@dataclass
class MonitorConfig:
    check_interval_minutes: int = 15  # zmień tutaj
```

## Struktura projektu

```
.
├── config.py          # Konfiguracja (opery, email, interwały)
├── models.py          # Modele danych
├── scrapers.py        # Web scrapery dla każdej opery
├── notifier.py        # System powiadomień email
├── monitor.py         # Główna pętla monitora
├── lambda_handler.py  # Handler AWS Lambda
├── requirements.txt   # Zależności Python
├── Dockerfile         # Do deploymentu kontenerowego
├── docker-compose.yml # Lokalne testowanie
└── aws/
    ├── template.yaml      # SAM template (zalecane)
    └── cloudformation.yml # CloudFormation template
```

## Jak to działa?

1. **Scraping** - co 15 minut program pobiera strony repertuarowe wszystkich oper
2. **Parsowanie** - szuka w HTML wzmianek o "Halka" lub "Straszny Dwór"
3. **Wykrywanie** - sprawdza czy bilety są dostępne
4. **Powiadomienie** - jeśli znajdzie nowe bilety, wysyła email
5. **Pamięć** - zapisuje o czym już powiadomił (plik `monitor_state.json`)

## Troubleshooting

### Email nie dochodzi

1. Sprawdź czy używasz **App Password**, nie zwykłego hasła
2. Sprawdź folder spam
3. Upewnij się że 2FA jest włączone na koncie Gmail

### Scraper nie znajduje spektakli

Strony oper się zmieniają. Jeśli scraper przestał działać dla konkretnej opery:

1. Sprawdź logi (`opera_monitor.log`)
2. Otwórz stronę repertuaru opery w przeglądarce
3. Zaktualizuj selektory w `scrapers.py`

### Lambda timeout

Zwiększ timeout w `template.yaml` (max 15 minut dla Lambda).

## Licencja

MIT - używaj jak chcesz! 🎵
