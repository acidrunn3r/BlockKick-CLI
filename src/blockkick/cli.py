"""BlockKick CLI - command line interface for wallet management."""

import typer
import json
import datetime
from getpass import getpass
from rich.console import Console
from rich.table import Table

from .wallet.keystore import create_keystore, KEYSTORE_DIR

app = typer.Typer(
    name="blockkick",
    help="BlockKick CLI — локальный кошелёк для blockchain Kickstarter",
    rich_markup_mode="rich",
    no_args_is_help=True,
)
console = Console()


# ==== WALLET COMMANDS ====
wallet_app = typer.Typer(help="Wallet management commands (create, list, info)")
app.add_typer(wallet_app, name="wallet")

@wallet_app.command("create")
def wallet_create(
    password: str = typer.Option(
        None, "--password", "-p",
        hide_input=True,
        confirmation_prompt=True,
        help="Пароль для шифрования keystore (запрашивается интерактивно, если не указан)"
    )
):
    """
    Create a new Ed25519 wallet and save it as encrypted keystore.
    
    The private key is encrypted using scrypt + AES-256-GCM.
    """
    try:
        if password is None:
            console.print("[bold]Создание нового кошелька[/bold]")
            while True:
                pwd = getpass("Введите пароль для кошелька (минимум 8 символов): ")
                if len(pwd) < 8:
                    console.print("[red]Пароль слишком короткий![/red]")
                    continue
                pwd2 = getpass("Повторите пароль: ")
                if pwd != pwd2:
                    console.print("[red]Пароли не совпадают. Попробуйте ещё раз.[/red]")
                    continue
                password = pwd
                break
        
        keystore_path = create_keystore(password=password)
        
        console.print(f"\n[green]Кошелёк успешно создан и зашифрован![/green]")
        # console.print(f"Адрес / Public key: {wallet['public_key_hex']}")
        console.print(f"Файл сохранён: [bold]{keystore_path}[/bold]")
        console.print(f"[red]Никому не передавайте этот файл и пароль![/red]")

    except Exception as e:
        console.print(f"[red]Ошибка при создании кошелька: {e}[/red]")
        raise typer.Exit(1)

@wallet_app.command("list")
def wallet_list():
    """
    List all local keystores found in ~/.blockkick/keystores/.
    
    Shows public key (short), timestamp and file path.
    """
    keystores = list(KEYSTORE_DIR.glob("keystore-*.json"))
    
    if not keystores:
        console.print("[yellow]Кошельки не найдены. Создайте свой первый кошелёк: blockkick wallet create[/yellow]")
        return
    
    table = Table(title=f"Найдено кошельков: {len(keystores)}", show_lines=True)
    table.add_column("№", style="dim", width=4)
    table.add_column("Public Key", style="cyan", no_wrap=True)
    table.add_column("Created", style="magenta")
    table.add_column("File", style="green")
    
    for idx, path in enumerate(sorted(keystores), 1):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pub_short = f"{data['public_key_hex'][:16]}..."
            ts = datetime.datetime.fromtimestamp(data["timestamp"]).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pub_short = "???"
            ts = "unknown"
        
        table.add_row(str(idx), pub_short, ts, path.name)
    
    console.print(table)
    console.print(f"[dim]Путь к хранилищу: {KEYSTORE_DIR}[/dim]")

@wallet_app.command("info")
def wallet_info(
    filename: str = typer.Argument(..., help="Имя файла keystore (например, keystore-abc123.json)")
):
    """
    Show details of a specific keystore file.
    
    Displays public key, creation timestamp, encryption params (without private key!).
    """
    filepath = KEYSTORE_DIR / filename
    
    if not filepath.exists():
        console.print(f"[red]Файл не найден: {filepath}[/red]")
        raise typer.Exit(1)
    
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        
        console.print(f"[bold]Информация о кошельке: {filename}[/bold]")
        console.print(f"🔑 Public Key: [bold]{data['public_key_hex']}[/bold]")
        console.print(f"🕐 Created: {data['timestamp']} ({__import__('datetime').datetime.fromtimestamp(data['timestamp'])})")
        console.print(f"🔐 Cipher: {data['crypto']['cipher'].upper()}")
        console.print(f"🧮 KDF: {data['crypto']['kdf']} (n={data['crypto']['kdfparams']['n']}, r={data['crypto']['kdfparams']['r']}, p={data['crypto']['kdfparams']['p']})")
        console.print(f"📄 Version: {data['version']}")
        
    except json.JSONDecodeError:
        console.print(f"[red]Ошибка чтения JSON в файле[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Ошибка: {e}[/red]")
        raise typer.Exit(1)


# ==== GENERAL COMMANDS ====
@app.command("version")
def show_version():
    """Show BlockKick CLI version."""
    from importlib.metadata import version
    pkg_version = version("blockkick")
    console.print(f"[bold]BlockKick CLI[/bold] v{pkg_version}")


if __name__ == "__main__":
    app()