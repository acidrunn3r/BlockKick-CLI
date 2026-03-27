"""BlockKick CLI - command line interface for wallet management."""

import typer
import json
import datetime
from getpass import getpass
from rich.console import Console
from rich.table import Table

from .wallet.keystore import create_keystore, KEYSTORE_DIR, decrypt_keystore

app = typer.Typer(
    name="blockkick",
    help="BlockKick CLI — local wallet for BlockKick blockhain",
    rich_markup_mode="rich",
    no_args_is_help=True,
)
console = Console()
_unlocked_wallet: dict[str, bytes] | None = None


# ==== WALLET COMMANDS ====
wallet_app = typer.Typer(help="Wallet management commands (create, list, info)")
app.add_typer(wallet_app, name="wallet")

@wallet_app.command("create")
def wallet_create(
    password: str = typer.Option(
        None, "--password", "-p",
        hide_input=True,
        confirmation_prompt=True,
        help="Wallet password. Used for encrypting and decrypting keystore"
    )
):
    """
    Create a new Ed25519 wallet and save it as encrypted keystore.
    
    The private key is encrypted using scrypt + AES-256-GCM.
    """
    try:
        if password is None:
            console.print("[bold]Creating new wallet..[/bold]")
            while True:
                pwd = getpass("Enter password (minimum 8 characters): ")
                if len(pwd) < 8:
                    console.print("[red]Password is too short. Try again.[/red]")
                    continue
                pwd2 = getpass("Confirm password: ")
                if pwd != pwd2:
                    console.print("[red]Passwords didn’t match. Try again.[/red]")
                    continue
                password = pwd
                break
        
        keystore_path, public_key = create_keystore(password=password)
        
        console.print(f"\n[green]Wallet successfully created and encrypted![/green]")
        console.print(f"Public key: {public_key}")
        console.print(f"File path: [bold]{keystore_path}[/bold]")
        console.print(f"Remeber your password! It will be used to acces your wallet.")
        console.print(f"[red]Do not give this file or password to anyone![/red]")

    except Exception as e:
        console.print(f"[red]Error when creating wallet: {e}[/red]")
        raise typer.Exit(1)

@wallet_app.command("list")
def wallet_list():
    """
    List all local keystores found in ~/.blockkick/keystores/.
    
    Shows public key (short), timestamp and file path.
    """
    keystores = list(KEYSTORE_DIR.glob("keystore-*.json"))
    
    if not keystores:
        console.print(
            "No wallets found." 
            "Create your first wallet: [yellow]blockkick wallet create[/yellow]"
        )
        return
    
    table = Table(title=f"Wallets found: {len(keystores)}", show_lines=True)
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
    console.print(f"[dim]Storage path: {KEYSTORE_DIR}[/dim]")

@wallet_app.command("info")
def wallet_info(
    filename: str = typer.Argument(
        ...,
        help="Keystore file name (e.g. keystore-abc123.json)"
    )
):
    """
    Show details of a specific keystore file.
    
    Displays public key, creation timestamp, encryption params (without private key!).
    """
    filepath = KEYSTORE_DIR / filename
    
    if not filepath.exists():
        console.print(f"[red]File not found: [/red]{filepath}")
        raise typer.Exit(1)
    
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        
        console.print(f"[bold]Wallet info: {filename}[/bold]")
        console.print(f"Public key [bold]{data['public_key_hex']}[/bold]")
        console.print(
            f"Created: {data['timestamp']} "
            f"({__import__('datetime').datetime.fromtimestamp(data['timestamp'])})"
        )
        console.print(f"Cipher: {data['crypto']['cipher'].upper()}")
        console.print(
            f"KDF: {data['crypto']['kdf']} "
            f"(n={data['crypto']['kdfparams']['n']}, "
            f"r={data['crypto']['kdfparams']['r']}, "
            f"p={data['crypto']['kdfparams']['p']})"
        )
        console.print(f"Version: {data['version']}")
        
    except json.JSONDecodeError:
        console.print(f"[red]Error reading JSON[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

@wallet_app.command("unlock")
def wallet_unlock(
    filename: str = typer.Argument(..., help="Keystore file name"),
    password: str = typer.Option(
        None, "--password", "-p",
        hide_input=True,
        help="Wallet password"
    ),
):
    """
    Unlock a wallet, locking currently unlocked wallet.
    
    The decrypted key is stored temporarily in memory for signing transactions.
    """
    global _unlocked_wallet
    
    filepath = KEYSTORE_DIR / filename
    
    if not filepath.exists():
        console.print(f"[red]File not found:[/red] {filepath}")
        raise typer.Exit(1)
    
    try:
        if _unlocked_wallet:
            old_filename = list(_unlocked_wallet.keys())[0]
            console.print(f"[dim]Disabling current wallet: {old_filename}[/dim]")
            _unlocked_wallet = None
        
        if password is None:
            password = getpass("Enter wallet password: ")
        
        private_key_bytes = decrypt_keystore(filepath, password)
        
        _unlocked_wallet = {filename: private_key_bytes}
        
        data = json.loads(filepath.read_text(encoding="utf-8"))
        public_key = data["public_key_hex"]
        
        console.print(f"\n[green]Wallet unlocked![/green]")
        console.print(f"Public key: [bold]{public_key}[/bold]")
        console.print(f"File: [bold]{filename}[/bold]")
        console.print(f"[dim]Private key is active untill the end of this session[/dim]")
        
    except ValueError as e:
        console.print(f"[red]Decrpytion error:[/red]{e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Unknown error:[/red]{e}")
        raise typer.Exit(1)

@wallet_app.command("lock")
def wallet_lock():
    """
    Lock the currently unlocked wallet.
    """
    global _unlocked_wallet
    
    if _unlocked_wallet:
        filename = list(_unlocked_wallet.keys())[0]
        _unlocked_wallet = None
        console.print(f"[green]Wallet locked: {filename}[/green]")
    else:
        console.print("There is no unlocked wallet.")

@wallet_app.command("status")
def wallet_status():
    """
    Show status of the currently unlocked wallet.
    """
    if not _unlocked_wallet:
        console.print("There is no unlocked wallet.")
        console.print("[dim]Use: blockkick wallet unlock <Keystore file name>[/dim]")
        return
    
    filename = list(_unlocked_wallet.keys())[0]
    data = json.loads((KEYSTORE_DIR / filename).read_text(encoding="utf-8"))
    public_key = data["public_key_hex"]
    
    console.print(f"[green]Currently unlocked wallet:[/green]")
    console.print(f"File: [bold]{filename}[/bold]")
    console.print(f"Public Key: [bold]{public_key}[/bold]")

# ==== GENERAL COMMANDS ====
@app.command("version")
def show_version():
    """Show BlockKick CLI version."""
    from importlib.metadata import version
    pkg_version = version("blockkick")
    console.print(f"[bold]BlockKick CLI[/bold] v{pkg_version}")


if __name__ == "__main__":
    app()
