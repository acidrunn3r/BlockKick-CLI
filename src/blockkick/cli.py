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
    get_api_url,
    set_api_url,
    save_api_tokens,
    get_api_access_token,
    clear_api_tokens,
    get_session_private_key,
)
from .blockchain.mining import fetch_candidate, mine, submit_block
from .api.client import request_challenge, auth_login, update_profile, get_profile
import httpx
import binascii
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

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

# ==== CONFIG COMMANDS ====
config_app = typer.Typer(help="Configuration commands (node URL, etc.)")
app.add_typer(config_app, name="config")

@config_app.command("set-node")
def config_set_node(
    url: str = typer.Argument(..., help="Node URL (e.g. http://localhost:3000)")
):
    """
    Set the default node URL for all commands (mine, balance, etc.).

    Persisted to ~/.blockkick/config.json.
    """
    set_node_url(url)
    console.print(f"[green]Node URL set to:[/green] [bold]{url}[/bold]")

@config_app.command("set-api")
def config_set_api(
    url: str = typer.Argument(..., help="API URL (e.g. http://localhost:8000)")
):
    """
    Set the default BlockKick API URL for register, login, etc.

    Persisted to ~/.blockkick/config.json.
    """
    set_api_url(url)
    console.print(f"[green]API URL set to:[/green] [bold]{url}[/bold]")

@config_app.command("show")
def config_show():
    """
    Show current configuration.
    """
    node_url = get_node_url()
    api_url = get_api_url()
    selected = get_selected_wallet()
    token = get_api_access_token()

    console.print(f"Node URL:        [bold]{node_url}[/bold]")
    console.print(f"API URL:         [bold]{api_url}[/bold]")
    console.print(f"Selected wallet: [bold]{selected or '—'}[/bold]")
    console.print(f"API logged in:   [bold]{'yes' if token else 'no'}[/bold]")


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


# ==== BALANCE COMMAND ====

@app.command("balance")
def balance_cmd(
    node: str = typer.Option(
        None, "--node", "-n",
        help="Node URL. Defaults to saved config."
    ),
):
    """
    Show the coin balance of the currently selected wallet.
    """
    selected = get_selected_wallet()

    if not selected:
        console.print("[red]No wallet selected.[/red]")
        console.print("[dim]Run: blockkick wallet select <filename>[/dim]")
        raise typer.Exit(1)

    try:
        data = json.loads((KEYSTORE_DIR / selected).read_text(encoding="utf-8"))
        public_key = data["public_key_hex"]
    except Exception as e:
        console.print(f"[red]Error reading wallet:[/red] {e}")
        raise typer.Exit(1)

    node_url = node or get_node_url()

    try:
        response = httpx.get(
            f"{node_url.rstrip('/')}/api/v1/balance/{public_key}",
            timeout=10,
        )
        response.raise_for_status()
        balance = response.json()["balance"]
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach node:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"Wallet:  [bold]{selected}[/bold]")
    console.print(f"Balance: [bold green]{balance} coins[/bold green]")


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


def _resolve_private_key(password: str | None) -> tuple[str, bytes, str]:
    """Return (wallet_filename, private_key_bytes, public_key_hex).

    Tries the session first; falls back to prompting for password if a wallet
    is selected but no session is active.

    Raises:
        typer.Exit: If no wallet is available.
    """
    import json as _json

    session_filename, private_key_bytes = get_session_private_key()

    if session_filename and private_key_bytes:
        data = _json.loads((KEYSTORE_DIR / session_filename).read_text(encoding="utf-8"))
        return session_filename, private_key_bytes, data["public_key_hex"]

    selected = get_selected_wallet()
    if not selected:
        console.print("[red]No wallet selected.[/red]")
        console.print("[dim]Run: blockkick wallet select <filename>[/dim]")
        raise typer.Exit(1)

    filepath = KEYSTORE_DIR / selected
    if password is None:
        from getpass import getpass as _getpass
        password = _getpass("Enter wallet password: ")

    try:
        private_key_bytes = decrypt_keystore(filepath, password)
    except ValueError as e:
        console.print(f"[red]Decryption error:[/red] {e}")
        raise typer.Exit(1)

    data = _json.loads(filepath.read_text(encoding="utf-8"))
    return selected, private_key_bytes, data["public_key_hex"]


# ==== AUTH COMMANDS ====

@app.command("register")
def register_cmd(
    name: str = typer.Option(
        None, "--name",
        help="Display name to set on your profile after registering."
    ),
    bio: str = typer.Option(
        "", "--bio",
        help="Short bio to set on your profile after registering."
    ),
    api: str = typer.Option(
        None, "--api",
        help="API URL. Defaults to saved config."
    ),
    password: str = typer.Option(
        None, "--password", "-p",
        hide_input=True,
        help="Wallet password (if no active session)."
    ),
):
    """
    Register your wallet with the BlockKick API.

    Performs a cryptographic challenge-response with your active wallet,
    creating a new account if one doesn't exist yet. Optionally sets a
    display name and bio on your profile.
    """
    wallet_file, private_key_bytes, public_key = _resolve_private_key(password)
    api_url = api or get_api_url()

    console.print(f"[bold]Wallet:[/bold] {wallet_file}")
    console.print(f"[bold]API:[/bold] {api_url}")

    try:
        console.print("\n[dim]Requesting challenge...[/dim]")
        nonce = request_challenge(api_url, public_key)
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach API:[/red] {e}")
        raise typer.Exit(1)

    private_key_obj = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    signature_hex = binascii.hexlify(private_key_obj.sign(nonce.encode("utf-8"))).decode()

    try:
        console.print("[dim]Submitting signature...[/dim]")
        tokens = auth_login(api_url, public_key, nonce, signature_hex)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Authentication failed:[/red] {e.response.text}")
        raise typer.Exit(1)
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach API:[/red] {e}")
        raise typer.Exit(1)

    save_api_tokens(tokens["access_token"], tokens["refresh_token"])

    if name:
        try:
            console.print("[dim]Setting profile...[/dim]")
            update_profile(api_url, tokens["access_token"], name, bio)
        except httpx.HTTPError as e:
            console.print(f"[yellow]Warning: profile update failed:[/yellow] {e}")

    console.print(f"\n[green bold]Registered![/green bold]")
    console.print(f"Wallet: [bold]{public_key[:16]}...[/bold]")
    if name:
        console.print(f"Name:   [bold]{name}[/bold]")
    console.print(f"[dim]Token saved. Use blockkick login to refresh.[/dim]")


@app.command("login")
def login_cmd(
    api: str = typer.Option(
        None, "--api",
        help="API URL. Defaults to saved config."
    ),
    password: str = typer.Option(
        None, "--password", "-p",
        hide_input=True,
        help="Wallet password (if no active session)."
    ),
):
    """
    Log in to the BlockKick API with your active wallet.

    Performs a cryptographic challenge-response and stores the JWT token
    locally for subsequent API commands.
    """
    wallet_file, private_key_bytes, public_key = _resolve_private_key(password)
    api_url = api or get_api_url()

    console.print(f"[bold]Wallet:[/bold] {wallet_file}")
    console.print(f"[bold]API:[/bold] {api_url}")

    try:
        console.print("\n[dim]Requesting challenge...[/dim]")
        nonce = request_challenge(api_url, public_key)
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach API:[/red] {e}")
        raise typer.Exit(1)

    private_key_obj = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    signature_hex = binascii.hexlify(private_key_obj.sign(nonce.encode("utf-8"))).decode()

    try:
        console.print("[dim]Submitting signature...[/dim]")
        tokens = auth_login(api_url, public_key, nonce, signature_hex)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Authentication failed:[/red] {e.response.text}")
        raise typer.Exit(1)
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach API:[/red] {e}")
        raise typer.Exit(1)

    save_api_tokens(tokens["access_token"], tokens["refresh_token"])

    try:
        profile = get_profile(api_url, tokens["access_token"])
        display = profile.get("display_name") or public_key[:16] + "..."
    except httpx.HTTPError:
        display = public_key[:16] + "..."

    console.print(f"\n[green bold]Logged in![/green bold]")
    console.print(f"Account: [bold]{display}[/bold]")
    console.print(f"Wallet:  [bold]{public_key[:16]}...[/bold]")


def _require_token(api: str | None) -> tuple[str, str]:
    """Return (api_url, access_token) or exit with a helpful message."""
    api_url = api or get_api_url()
    token = get_api_access_token()
    if not token:
        console.print("[red]Not logged in.[/red]")
        console.print("[dim]Run: blockkick login[/dim]")
        raise typer.Exit(1)
    return api_url, token


# ==== PROFILE COMMANDS ====

profile_app = typer.Typer(help="Manage your BlockKick API profile.")
app.add_typer(profile_app, name="profile")


@profile_app.command("show")
def profile_show(
    api: str = typer.Option(
        None, "--api",
        help="API URL. Defaults to saved config."
    ),
):
    """
    Show your BlockKick API profile.

    Fetches and displays display name, bio and wallet address from the API.
    """
    api_url, token = _require_token(api)

    try:
        data = get_profile(api_url, token)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            console.print("[red]Session expired.[/red]")
            console.print("[dim]Run: blockkick login[/dim]")
        else:
            console.print(f"[red]API error:[/red] {e.response.text}")
        raise typer.Exit(1)
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach API:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"Wallet:  [bold]{data['wallet_address']}[/bold]")
    console.print(f"Name:    [bold]{data.get('display_name') or '—'}[/bold]")
    console.print(f"Bio:     [bold]{data.get('bio') or '—'}[/bold]")


@profile_app.command("update")
def profile_update(
    name: str = typer.Option(
        ..., "--name",
        help="New display name (max 100 characters)."
    ),
    bio: str = typer.Option(
        "", "--bio",
        help="Short bio."
    ),
    api: str = typer.Option(
        None, "--api",
        help="API URL. Defaults to saved config."
    ),
):
    """
    Update your BlockKick API profile.

    Sets a new display name and optional bio on your account.
    """
    api_url, token = _require_token(api)

    try:
        data = update_profile(api_url, token, name, bio)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            console.print("[red]Session expired.[/red]")
            console.print("[dim]Run: blockkick login[/dim]")
        else:
            console.print(f"[red]API error:[/red] {e.response.text}")
        raise typer.Exit(1)
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach API:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[green]Profile updated![/green]")
    console.print(f"Name: [bold]{data.get('display_name')}[/bold]")
    if data.get("bio"):
        console.print(f"Bio:  [bold]{data['bio']}[/bold]")


if __name__ == "__main__":
    app()
