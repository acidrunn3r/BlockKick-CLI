# BlockKick-CLI
**Локальный кошелёк для взаимодействия с платформой BlockKick**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)

Связанные репозитории:
- [BlockKick](https://github.com/andre1vorobei/BlockKick)
- [BlockKick-API](https://github.com/acidrunn3r/BlockKick-API)

## Установка

### Требования
- Python 3.11 или выше
- pip

### Шаг 1: Склонируйте репозиторий
```bash
git clone https://github.com/acidrunn3r/BlockKick-CLI.git
cd BlockKick-CLI
```
### Шаг 2: Создайте и активируйте виртуальное окружение
```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\Activate.ps1  # Windows (PowerShell)
```
### Шаг 3: Установите пакет
```bash
pip install -e .
```
#### Для использования клиента вне виртуального окружения
```bash
python -m pip install --user pipx
pipx ensurepath
pipx install git+https://github.com/acidrunn3r/BlockKick-CLI.git
```
### Шаг 4: Настройте автодополнение (опционально)
```bash
blockkick --install-completion
```
#### Теперь можно использовать автодополнение по клавише **Tab**

## Разработка

### Требования
- Python 3.11 или выше
- [Poetry](https://python-poetry.org/)

### Шаг 1: Установите зависимости
```bash
poetry install --with dev
```
### Шаг 2: Установите pre-commit хуки
```bash
poetry run pre-commit install
```
### Шаг 3: Запустите тесты
```bash
make test
```
#### Линтинг и форматирование
```bash
make lint    # проверка
make format  # автоисправление
```

## Команды

### `blockkick config`
Настройка CLI.
- `set-node <url>` — задать URL ноды блокчейна
- `set-api <url>` — задать URL BlockKick API
- `show` — показать текущую конфигурацию

### `blockkick wallet`
Управление локальными кошельками.
- `create` — создать новый кошелёк (Ed25519, шифрование AES-256-GCM)
- `list` — список всех кошельков
- `info <filename>` — детали конкретного кошелька
- `select <filename>` — выбрать активный кошелёк
- `deselect` — снять выбор и очистить сессию

### `blockkick balance`
Показать баланс активного кошелька.

### `blockkick mine`
Добыть блок на BlockKick блокчейне (Proof-of-Work).

### `blockkick register`
Зарегистрировать кошелёк в BlockKick API через криптографический challenge-response.

### `blockkick login`
Войти в BlockKick API и сохранить JWT-токен локально.

### `blockkick profile`
Управление профилем в BlockKick API.
- `show` — показать профиль
- `update` — обновить имя и bio

### `blockkick projects`
Показать список краудфандинговых проектов на BlockKick.
