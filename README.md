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
#### Для использование клиента вне виртуального окружения
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
