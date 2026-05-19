"""BlockKick CLI - command line interface for wallet management."""

import typer
import json
import datetime
from getpass import getpass
from rich.console import Console
from rich.table import Table

from .wallet.keystore import (
    create_keystore,
    KEYSTORE_DIR,
    decrypt_keystore,
    get_selected_wallet,
    set_selected_wallet,
    save_session,
    clear_session,
    get_last_action,
    update_last_action,
    get_node_url,
    set_node_url,
)
from .blockchain.mining import fetch_candidate, mine, submit_block

console = Console()

app = typer.Typer(
    name="blockkick",
    help="BlockKick CLI — local wallet for BlockKick blockchain",
    rich_markup_mode="rich",
    no_args_is_help=True,
    context_settings={
        "help_option_names": ["-h", "--help"]
    },
)

# ==== GENERAL COMMANDS ====
def _version_callback(value: bool):
    """Callback for --version flag."""
    if value:
        from importlib.metadata import version
        try:
            pkg_version = version("blockkick")
        except Exception:
            pkg_version = "0.1.0 (dev)"
        typer.echo(f"BlockKick CLI v{pkg_version}")
        raise typer.Exit()

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version", "-v",
        help="Show version and exit",
        is_eager=True,
        callback=_version_callback,
    ),
):
    """BlockKick CLI — local wallet for BlockKick blockchain."""
    pass

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
        update_last_action(keystore_path.name)

        console.print(f"\n[green]Wallet successfully created and encrypted![/green]")
        console.print(f"Public key: {public_key}")
        console.print(f"File path: [bold]{keystore_path}[/bold]")
        console.print(f"Remember your password! It will be used to access your wallet.")
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
            "No wallets found. " 
            "Create your first wallet: [yellow]blockkick wallet create[/yellow]"
        )
        return
    
    selected = get_selected_wallet()

    def sort_key(path):
        last = get_last_action(path.name)
        if last is not None:
            return last
        try:
            return json.loads(path.read_text(encoding="utf-8"))["timestamp"]
        except Exception:
            return 0

    sorted_keystores = sorted(keystores, key=sort_key, reverse=True)

    table = Table(title=f"Wallets found: {len(keystores)}", show_lines=True)
    table.add_column("№", style="dim", width=4)
    table.add_column("Public Key", style="cyan", no_wrap=True)
    table.add_column("Last Action", style="magenta")
    table.add_column("File", style="green")
    table.add_column("", width=2)

    for idx, path in enumerate(sorted_keystores, 1):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pub_short = f"{data['public_key_hex'][:16]}..."
            last = get_last_action(path.name) or data["timestamp"]
            ts = datetime.datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pub_short = "???"
            ts = "unknown"

        active = "*" if path.name == selected else ""
        table.add_row(str(idx), pub_short, ts, path.name, active)
    
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

@wallet_app.command("select")
def wallet_select(
    filename: str = typer.Argument(..., help="Keystore file name (e.g. keystore-abc123.json)"),
    password: str = typer.Option(
        None, "--password", "-p",
        hide_input=True,
        help="Wallet password"
    ),
):
    """
    Select a wallet as the active one for future commands (mine, login, etc.).

    Decrypts the keystore to verify the password, then persists the wallet
    selection and the decrypted key to ~/.blockkick/ for future use.
    """
    filepath = KEYSTORE_DIR / filename

    if not filepath.exists():
        console.print(f"[red]File not found:[/red] {filepath}")
        raise typer.Exit(1)

    try:
        if password is None:
            password = getpass("Enter wallet password: ")

        private_key_bytes = decrypt_keystore(filepath, password)

        data = json.loads(filepath.read_text(encoding="utf-8"))
        public_key = data["public_key_hex"]
    except ValueError as e:
        console.print(f"[red]Decryption error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    set_selected_wallet(filename)
    save_session(filename, private_key_bytes)
    update_last_action(filename)

    console.print(f"[green]Active wallet set to:[/green] [bold]{filename}[/bold]")
    console.print(f"Public key: [bold]{public_key}[/bold]")
    console.print(f"[dim]This wallet will be used by blockkick mine, blockkick login, etc.[/dim]")


@wallet_app.command("deselect")
def wallet_deselect():
    """
    Deselect the active wallet and clear the session.
    """
    selected = get_selected_wallet()

    if not selected:
        console.print("No wallet is currently selected.")
        return

    clear_session()
    set_selected_wallet("")

    console.print(f"[green]Wallet deselected:[/green] {selected}")


# ==== MINE COMMAND ====

@app.command("mine")
def mine_cmd(
    node: str = typer.Option(
        None, "--node", "-n",
        help="Node URL (e.g. http://localhost:8080). Defaults to saved config."
    ),
):
    """
    Mine a block on the BlockKick blockchain.

    Uses the currently selected wallet as the reward recipient.
    Runs proof-of-work locally and submits the block to the node.
    """
    from .wallet.keystore import get_session_private_key, KEYSTORE_DIR
    import json as _json

    # Resolve wallet
    session_filename, _ = get_session_private_key()
    selected = get_selected_wallet()
    wallet_file = session_filename or selected

    if not wallet_file:
        console.print("[red]No wallet selected.[/red]")
        console.print("[dim]Run: blockkick wallet select <filename>[/dim]")
        raise typer.Exit(1)

    try:
        data = _json.loads((KEYSTORE_DIR / wallet_file).read_text(encoding="utf-8"))
        public_key = data["public_key_hex"]
    except Exception as e:
        console.print(f"[red]Error reading wallet:[/red] {e}")
        raise typer.Exit(1)

    # Resolve node URL
    node_url = node or get_node_url()
    if node:
        set_node_url(node)

    console.print(f"[bold]Mining with wallet:[/bold] {wallet_file}")
    console.print(f"[bold]Node:[/bold] {node_url}")
    console.print(f"[bold]Public key:[/bold] {public_key[:16]}...")

    # Fetch candidate
    try:
        console.print("\n[dim]Fetching block candidate...[/dim]")
        candidate = fetch_candidate(node_url, public_key)
    except Exception as e:
        console.print(f"[red]Failed to reach node:[/red] {e}")
        raise typer.Exit(1)

    difficulty = candidate["difficulty"]
    reward = candidate["reward"]
    block_index = candidate["block_template"]["index"]

    console.print(f"Block [bold]#{block_index}[/bold] | Difficulty: [bold]{difficulty}[/bold] | Reward: [bold]{reward}[/bold] coins")
    console.print(f"\n[yellow]Mining...[/yellow] (looking for {difficulty} leading zeros)\n")

    # Run PoW
    try:
        with console.status("[yellow]Hashing...[/yellow]", spinner="dots"):
            nonce, block_hash, elapsed = mine(candidate)
    except KeyboardInterrupt:
        console.print("\n[red]Mining cancelled.[/red]")
        raise typer.Exit(0)

    console.print(f"[green]Block found![/green]")
    console.print(f"Nonce:   [bold]{nonce}[/bold]")
    console.print(f"Hash:    [bold]{block_hash}[/bold]")
    console.print(f"Time:    [bold]{elapsed:.2f}s[/bold]")

    # Submit
    try:
        console.print("\n[dim]Submitting block...[/dim]")
        result = submit_block(node_url, candidate, nonce)
    except Exception as e:
        console.print(f"[red]Submission failed:[/red] {e}")
        raise typer.Exit(1)

    update_last_action(wallet_file)

    console.print(f"\n[green bold]Block accepted![/green bold]")
    console.print(f"Reward: [bold]{result.get('reward', reward)}[/bold] coins → {public_key[:16]}...")


if __name__ == "__main__":
    app()
