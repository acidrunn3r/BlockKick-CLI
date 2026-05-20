"""BlockKick CLI - command line interface for wallet management."""

import binascii
import datetime
import json
from getpass import getpass
from pathlib import Path

import httpx
import typer
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rich.console import Console
from rich.table import Table

from .api.client import (
    auth_login,
    get_balance,
    get_profile,
    get_project,
    get_transaction,
    get_wallet_transactions,
    list_projects,
    request_challenge,
    submit_transaction,
    update_profile,
)
from .blockchain.mining import fetch_candidate, mine, submit_block
from .blockchain.transactions import (
    build_create_project_tx,
    build_fund_project_tx,
    build_transfer_tx,
    get_signing_data,
)
from .blockchain.tx import sign_transaction
from .wallet.keystore import (
    KEYSTORE_DIR,
    clear_api_tokens,
    clear_session,
    create_keystore,
    decrypt_keystore,
    get_api_access_token,
    get_api_url,
    get_last_action,
    get_node_url,
    get_selected_wallet,
    get_session_private_key,
    save_api_tokens,
    save_session,
    set_api_url,
    set_node_url,
    set_selected_wallet,
    update_last_action,
)

console = Console()

app = typer.Typer(
    name="blockkick",
    help="BlockKick CLI — local wallet for BlockKick blockchain",
    rich_markup_mode="rich",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


# ==== GENERAL COMMANDS ====
def _version_callback(value: bool) -> None:
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
        "--version",
        "-v",
        help="Show version and exit",
        is_eager=True,
        callback=_version_callback,
    ),
) -> None:
    """BlockKick CLI — local wallet for BlockKick blockchain."""
    pass


# ==== CONFIG COMMANDS ====
config_app = typer.Typer(help="Configuration commands (node URL, etc.)")
app.add_typer(config_app, name="config")


@config_app.command("set-node")
def config_set_node(
    url: str = typer.Argument(..., help="Node URL (e.g. http://localhost:3000)")
) -> None:
    """
    Set the default node URL for all commands (mine, balance, etc.).

    Persisted to ~/.blockkick/config.json.
    """
    set_node_url(url)
    console.print(f"[green]Node URL set to:[/green] [bold]{url}[/bold]")


@config_app.command("set-api")
def config_set_api(
    url: str = typer.Argument(..., help="API URL (e.g. http://localhost:8000)")
) -> None:
    """
    Set the default BlockKick API URL for register, login, etc.

    Persisted to ~/.blockkick/config.json.
    """
    set_api_url(url)
    console.print(f"[green]API URL set to:[/green] [bold]{url}[/bold]")


@config_app.command("show")
def config_show() -> None:
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
        None,
        "--password",
        "-p",
        hide_input=True,
        confirmation_prompt=True,
        help="Wallet password. Used for encrypting and decrypting keystore",
    )
) -> None:
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

        console.print("\n[green]Wallet successfully created and encrypted![/green]")
        console.print(f"Public key: {public_key}")
        console.print(f"File path: [bold]{keystore_path}[/bold]")
        console.print("Remember your password! It will be used to access your wallet.")
        console.print("[red]Do not give this file or password to anyone![/red]")

    except Exception as e:
        console.print(f"[red]Error when creating wallet: {e}[/red]")
        raise typer.Exit(1) from None


@wallet_app.command("list")
def wallet_list() -> None:
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

    def sort_key(path: Path) -> int:
        last = get_last_action(path.name)
        if last is not None:
            return last
        try:
            return int(json.loads(path.read_text(encoding="utf-8"))["timestamp"])
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
        ..., help="Keystore file name (e.g. keystore-abc123.json)"
    )
) -> None:
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
        console.print("[red]Error reading JSON[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@wallet_app.command("select")
def wallet_select(
    filename: str = typer.Argument(
        ..., help="Keystore file name (e.g. keystore-abc123.json)"
    ),
    password: str = typer.Option(
        None, "--password", "-p", hide_input=True, help="Wallet password"
    ),
) -> None:
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
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    set_selected_wallet(filename)
    save_session(filename, private_key_bytes)
    update_last_action(filename)

    console.print(f"[green]Active wallet set to:[/green] [bold]{filename}[/bold]")
    console.print(f"Public key: [bold]{public_key}[/bold]")
    console.print(
        "[dim]This wallet will be used by blockkick mine, blockkick login, etc.[/dim]"
    )


@wallet_app.command("deselect")
def wallet_deselect() -> None:
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
        None, "--node", "-n", help="Node URL. Defaults to saved config."
    ),
) -> None:
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
        raise typer.Exit(1) from None

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
        raise typer.Exit(1) from None

    console.print(f"Wallet:  [bold]{selected}[/bold]")
    console.print(f"Balance: [bold green]{balance} coins[/bold green]")


# ==== MINE COMMAND ====


@app.command("mine")
def mine_cmd(
    node: str = typer.Option(
        None,
        "--node",
        "-n",
        help="Node URL (e.g. http://localhost:8080). Defaults to saved config.",
    ),
    watch: bool = typer.Option(
        False,
        "--watch",
        "-w",
        help="Mine continuously until Ctrl+C.",
    ),
) -> None:
    """
    Mine a block on the BlockKick blockchain.

    Uses the currently selected wallet as the reward recipient.
    Runs proof-of-work locally and submits the block to the node.
    Pass --watch to mine continuously until Ctrl+C.
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
        raise typer.Exit(1) from None

    # Resolve node URL
    node_url = node or get_node_url()

    console.print(f"[bold]Mining with wallet:[/bold] {wallet_file}")
    console.print(f"[bold]Node:[/bold] {node_url}")
    console.print(f"[bold]Public key:[/bold] {public_key[:16]}...")
    if watch:
        console.print("[dim]Watch mode — press Ctrl+C to stop.[/dim]")

    blocks_mined = 0
    while True:
        # Fetch candidate
        try:
            console.print("\n[dim]Fetching block candidate...[/dim]")
            candidate = fetch_candidate(node_url, public_key)
        except KeyboardInterrupt:
            console.print("\n[red]Mining cancelled.[/red]")
            raise typer.Exit(0) from None
        except Exception as e:
            console.print(f"[red]Failed to reach node:[/red] {e}")
            raise typer.Exit(1) from None

        difficulty = candidate["difficulty"]
        reward = candidate["reward"]
        block_index = candidate["block_template"]["index"]

        console.print(
            f"Block [bold]#{block_index}[/bold] | Difficulty: [bold]{difficulty}[/bold] | Reward: [bold]{reward}[/bold] coins"
        )
        console.print(
            f"\n[yellow]Mining...[/yellow] (looking for {difficulty} leading zeros)\n"
        )

        # Run PoW
        try:
            with console.status("[yellow]Hashing...[/yellow]", spinner="dots"):
                nonce, block_hash, elapsed = mine(candidate)
        except KeyboardInterrupt:
            console.print("\n[red]Mining cancelled.[/red]")
            raise typer.Exit(0) from None

        console.print("[green]Block found![/green]")
        console.print(f"Nonce:   [bold]{nonce}[/bold]")
        console.print(f"Hash:    [bold]{block_hash}[/bold]")
        console.print(f"Time:    [bold]{elapsed:.2f}s[/bold]")

        # Submit
        try:
            console.print("\n[dim]Submitting block...[/dim]")
            result = submit_block(node_url, candidate, nonce)
        except KeyboardInterrupt:
            console.print("\n[red]Mining cancelled.[/red]")
            raise typer.Exit(0) from None
        except Exception as e:
            console.print(f"[red]Submission failed:[/red] {e}")
            raise typer.Exit(1) from None

        update_last_action(wallet_file)
        blocks_mined += 1

        console.print("\n[green bold]Block accepted![/green bold]")
        console.print(
            f"Reward: [bold]{result.get('reward', reward)}[/bold] coins → {public_key[:16]}..."
        )

        if not watch:
            break

        console.print(
            f"\n[dim]Total mined this session: {blocks_mined}. Starting next block...[/dim]"
        )
        console.rule(style="dim")


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
        data = _json.loads(
            (KEYSTORE_DIR / session_filename).read_text(encoding="utf-8")
        )
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
        raise typer.Exit(1) from None

    data = _json.loads(filepath.read_text(encoding="utf-8"))
    return selected, private_key_bytes, data["public_key_hex"]


# ==== AUTH COMMANDS ====


@app.command("register")
def register_cmd(
    name: str = typer.Option(
        None, "--name", help="Display name to set on your profile after registering."
    ),
    bio: str = typer.Option(
        "", "--bio", help="Short bio to set on your profile after registering."
    ),
    api: str = typer.Option(None, "--api", help="API URL. Defaults to saved config."),
    password: str = typer.Option(
        None,
        "--password",
        "-p",
        hide_input=True,
        help="Wallet password (if no active session).",
    ),
) -> None:
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
        raise typer.Exit(1) from None

    private_key_obj = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    signature_hex = binascii.hexlify(
        private_key_obj.sign(nonce.encode("utf-8"))
    ).decode()

    try:
        console.print("[dim]Submitting signature...[/dim]")
        tokens = auth_login(api_url, public_key, nonce, signature_hex)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Authentication failed:[/red] {e.response.text}")
        raise typer.Exit(1) from None
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach API:[/red] {e}")
        raise typer.Exit(1) from None

    save_api_tokens(tokens["access_token"], tokens["refresh_token"])

    if name:
        try:
            console.print("[dim]Setting profile...[/dim]")
            update_profile(api_url, tokens["access_token"], name, bio)
        except httpx.HTTPError as e:
            console.print(f"[yellow]Warning: profile update failed:[/yellow] {e}")

    console.print("\n[green bold]Registered![/green bold]")
    console.print(f"Wallet: [bold]{public_key[:16]}...[/bold]")
    if name:
        console.print(f"Name:   [bold]{name}[/bold]")
    console.print("[dim]Token saved. Use blockkick login to refresh.[/dim]")


@app.command("login")
def login_cmd(
    api: str = typer.Option(None, "--api", help="API URL. Defaults to saved config."),
    password: str = typer.Option(
        None,
        "--password",
        "-p",
        hide_input=True,
        help="Wallet password (if no active session).",
    ),
) -> None:
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
        raise typer.Exit(1) from None

    private_key_obj = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    signature_hex = binascii.hexlify(
        private_key_obj.sign(nonce.encode("utf-8"))
    ).decode()

    try:
        console.print("[dim]Submitting signature...[/dim]")
        tokens = auth_login(api_url, public_key, nonce, signature_hex)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Authentication failed:[/red] {e.response.text}")
        raise typer.Exit(1) from None
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach API:[/red] {e}")
        raise typer.Exit(1) from None

    save_api_tokens(tokens["access_token"], tokens["refresh_token"])

    try:
        profile = get_profile(api_url, tokens["access_token"])
        display = profile.get("display_name") or public_key[:16] + "..."
    except httpx.HTTPError:
        display = public_key[:16] + "..."

    console.print("\n[green bold]Logged in![/green bold]")
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
    api: str = typer.Option(None, "--api", help="API URL. Defaults to saved config."),
) -> None:
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
        raise typer.Exit(1) from None
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach API:[/red] {e}")
        raise typer.Exit(1) from None

    console.print(f"Wallet:  [bold]{data['wallet_address']}[/bold]")
    console.print(f"Name:    [bold]{data.get('display_name') or '—'}[/bold]")
    console.print(f"Bio:     [bold]{data.get('bio') or '—'}[/bold]")


@profile_app.command("update")
def profile_update(
    name: str = typer.Option(
        ..., "--name", help="New display name (max 100 characters)."
    ),
    bio: str = typer.Option("", "--bio", help="Short bio."),
    api: str = typer.Option(None, "--api", help="API URL. Defaults to saved config."),
) -> None:
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
        raise typer.Exit(1) from None
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach API:[/red] {e}")
        raise typer.Exit(1) from None

    console.print("[green]Profile updated![/green]")
    console.print(f"Name: [bold]{data.get('display_name')}[/bold]")
    if data.get("bio"):
        console.print(f"Bio:  [bold]{data['bio']}[/bold]")


# ==== PROJECT COMMANDS ====

project_app = typer.Typer(help="Crowdfunding project commands (create, donate).")
app.add_typer(project_app, name="project")


@project_app.command("create")
def project_create(
    node: str = typer.Option(
        None, "--node", "-n", help="Node URL. Defaults to saved config."
    ),
    password: str = typer.Option(
        None,
        "--password",
        "-p",
        hide_input=True,
        help="Wallet password (if no active session).",
    ),
) -> None:
    """
    Create a new crowdfunding project on the BlockKick blockchain.

    Interactively prompts for project name, description, goal amount and
    deadline, then broadcasts a signed CreateProject transaction to the node.
    """
    wallet_file, private_key_bytes, public_key = _resolve_private_key(password)
    node_url = node or get_node_url()

    console.print("[bold]New project[/bold]")
    name = typer.prompt("Enter project name")
    description = typer.prompt("Enter project description")

    while True:
        try:
            goal = int(typer.prompt("Enter goal amount (coins)"))
            if goal < 1:
                console.print("[red]Goal must be at least 1 coin.[/red]")
                continue
            break
        except ValueError:
            console.print("[red]Please enter a valid number.[/red]")

    while True:
        try:
            days = int(typer.prompt("Enter deadline (days from now)", default="30"))
            if days < 1:
                console.print("[red]Deadline must be at least 1 day.[/red]")
                continue
            break
        except ValueError:
            console.print("[red]Please enter a valid number.[/red]")

    import time as _time

    deadline_ts = int(_time.time()) + days * 86400

    tx = build_create_project_tx(public_key, name, description, goal, deadline_ts)
    signing_data = get_signing_data(tx)
    signature = sign_transaction(signing_data, private_key_bytes)
    tx["signature"] = signature

    try:
        console.print("\n[dim]Submitting transaction...[/dim]")
        result = submit_transaction(node_url, tx)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Node rejected transaction:[/red] {e.response.text}")
        raise typer.Exit(1) from None
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach node:[/red] {e}")
        raise typer.Exit(1) from None

    update_last_action(wallet_file)

    project_id = tx["data"]["project_id"]
    status = result.get("status", "unknown")

    console.print("\n[green bold]Project created![/green bold]")
    console.print(f"Project ID: [bold]{project_id}[/bold]")
    console.print(f"Name:       [bold]{name}[/bold]")
    console.print(f"Goal:       [bold]{goal} coins[/bold]")
    console.print(f"TX status:  [bold]{status}[/bold]")
    console.print(f"[dim]TX ID: {tx['id']}[/dim]")


@project_app.command("donate")
def project_donate(
    project_id: str = typer.Argument(
        ...,
        help="Project ID (e.g. proj_abc1234...). Use 'blockkick projects' to list them.",
    ),
    node: str = typer.Option(
        None, "--node", "-n", help="Node URL. Defaults to saved config."
    ),
    password: str = typer.Option(
        None,
        "--password",
        "-p",
        hide_input=True,
        help="Wallet password (if no active session).",
    ),
) -> None:
    """
    Donate coins to a crowdfunding project.

    Checks your wallet balance before broadcasting a signed FundProject
    transaction to the node.
    """
    wallet_file, private_key_bytes, public_key = _resolve_private_key(password)
    node_url = node or get_node_url()

    while True:
        try:
            amount = int(typer.prompt("Enter amount of coins"))
            if amount < 1:
                console.print("[red]Amount must be at least 1 coin.[/red]")
                continue
            break
        except ValueError:
            console.print("[red]Please enter a valid number.[/red]")

    creator_wallet = typer.prompt("Enter creator wallet address")
    note = typer.prompt("Enter backer note (leave empty to skip)", default="")

    try:
        balance = get_balance(node_url, public_key)
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach node:[/red] {e}")
        raise typer.Exit(1) from None

    if balance < amount:
        console.print(
            f"[red]Insufficient balance.[/red] "
            f"You have [bold]{balance} coins[/bold] but the donation requires [bold]{amount} coins[/bold]."
        )
        raise typer.Exit(1)

    tx = build_fund_project_tx(public_key, creator_wallet, project_id, amount, note)
    signing_data = get_signing_data(tx)
    signature = sign_transaction(signing_data, private_key_bytes)
    tx["signature"] = signature

    try:
        console.print("\n[dim]Submitting transaction...[/dim]")
        result = submit_transaction(node_url, tx)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Node rejected transaction:[/red] {e.response.text}")
        raise typer.Exit(1) from None
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach node:[/red] {e}")
        raise typer.Exit(1) from None

    update_last_action(wallet_file)

    status = result.get("status", "unknown")

    console.print("\n[green bold]Donation sent![/green bold]")
    console.print(f"Project:   [bold]{project_id}[/bold]")
    console.print(f"Amount:    [bold]{amount} coins[/bold]")
    console.print(f"TX status: [bold]{status}[/bold]")
    console.print(f"[dim]TX ID: {tx['id']}[/dim]")


# ==== PROJECTS COMMAND ====


@app.command("projects")
def projects_cmd(
    api: str = typer.Option(None, "--api", help="API URL. Defaults to saved config."),
) -> None:
    """
    List all crowdfunding projects on BlockKick.
    """
    api_url = api or get_api_url()

    try:
        projects = list_projects(api_url)
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach API:[/red] {e}")
        raise typer.Exit(1) from None

    if not projects:
        console.print("No projects found yet.")
        return

    table = Table(title=f"Projects ({len(projects)})", show_lines=True)
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("Goal", justify="right", style="cyan")
    table.add_column("Raised", justify="right", style="green")
    table.add_column("Status", style="magenta")

    for p in projects:
        goal = str(p["goal_amount"])
        raised = str(p["raised_amount"])
        table.add_row(p["project_id"], p["name"], goal, raised, p["status"])

    console.print(table)


# ==== TRANSFER COMMAND ====


@app.command("transfer")
def transfer_cmd(
    address: str = typer.Argument(..., help="Recipient wallet address (64-char hex)."),
    amount: int = typer.Argument(..., help="Amount of coins to send (≥ 1)."),
    message: str = typer.Option(
        "", "--message", "-m", help="Optional note attached to the transfer."
    ),
    node: str = typer.Option(
        None, "--node", "-n", help="Node URL. Defaults to saved config."
    ),
    password: str = typer.Option(
        None,
        "--password",
        "-p",
        hide_input=True,
        help="Wallet password (if no active session).",
    ),
) -> None:
    """
    Send coins from your wallet to another address.

    Builds and signs a Transfer transaction then broadcasts it to the node.
    Use 'blockkick tx <tx_id>' to check whether it confirmed.
    """
    if amount < 1:
        console.print("[red]Amount must be at least 1 coin.[/red]")
        raise typer.Exit(1)

    wallet_file, private_key_bytes, public_key = _resolve_private_key(password)
    node_url = node or get_node_url()

    try:
        balance = get_balance(node_url, public_key)
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach node:[/red] {e}")
        raise typer.Exit(1) from None

    if balance < amount:
        console.print(
            f"[red]Insufficient balance.[/red] "
            f"You have [bold]{balance} coins[/bold] but the transfer requires [bold]{amount} coins[/bold]."
        )
        raise typer.Exit(1)

    tx = build_transfer_tx(public_key, address, amount, message)
    signing_data = get_signing_data(tx)
    signature = sign_transaction(signing_data, private_key_bytes)
    tx["signature"] = signature

    try:
        console.print("\n[dim]Submitting transaction...[/dim]")
        result = submit_transaction(node_url, tx)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Node rejected transaction:[/red] {e.response.text}")
        raise typer.Exit(1) from None
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach node:[/red] {e}")
        raise typer.Exit(1) from None

    update_last_action(wallet_file)

    status = result.get("status", "unknown")

    console.print("\n[green bold]Transfer sent![/green bold]")
    console.print(f"To:        [bold]{address[:16]}...[/bold]")
    console.print(f"Amount:    [bold]{amount} coins[/bold]")
    console.print(f"TX status: [bold]{status}[/bold]")
    console.print(f"[dim]TX ID: {tx['id']}[/dim]")


# ==== TX COMMAND ====


@app.command("tx")
def tx_cmd(
    tx_id: str = typer.Argument(..., help="Transaction ID (64-char hex)."),
    node: str = typer.Option(
        None, "--node", "-n", help="Node URL. Defaults to saved config."
    ),
) -> None:
    """
    Look up a transaction by ID and show its status and details.

    Useful for checking whether a transaction (transfer, donate, project
    create) has been confirmed into a block after submission.
    """
    node_url = node or get_node_url()

    try:
        data = get_transaction(node_url, tx_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            console.print(f"[red]Transaction not found:[/red] {tx_id}")
        else:
            console.print(f"[red]Node error:[/red] {e.response.text}")
        raise typer.Exit(1) from None
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach node:[/red] {e}")
        raise typer.Exit(1) from None

    console.print(f"TX ID:     [bold]{data.get('id', tx_id)}[/bold]")
    console.print(f"Type:      [bold]{data.get('tx_type', '—')}[/bold]")
    console.print(f"From:      [bold]{data.get('from', '—')}[/bold]")
    if data.get("to"):
        console.print(f"To:        [bold]{data['to']}[/bold]")
    console.print(f"Status:    [bold]{data.get('status', '—')}[/bold]")
    if data.get("block_index") is not None:
        console.print(f"Block:     [bold]#{data['block_index']}[/bold]")
    tx_data = data.get("data", {})
    if tx_data:
        console.print(f"Data:      [bold]{tx_data}[/bold]")


# ==== HISTORY COMMAND ====


@app.command("history")
def history_cmd(
    api: str = typer.Option(None, "--api", help="API URL. Defaults to saved config."),
) -> None:
    """
    Show your wallet's transaction history.

    Displays all confirmed transfers, donations, and project events where
    your wallet is the sender or recipient, newest first.
    """
    selected = get_selected_wallet()
    if not selected:
        console.print(
            "[red]No wallet selected.[/red] Run: blockkick wallet select <file>"
        )
        raise typer.Exit(1)
    keystore_path = KEYSTORE_DIR / selected
    keystore_data = json.loads(keystore_path.read_text(encoding="utf-8"))
    public_key: str = keystore_data["public_key_hex"]
    api_url = api or get_api_url()

    try:
        txs = get_wallet_transactions(api_url, public_key)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]API error:[/red] {e.response.text}")
        raise typer.Exit(1) from None
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach API:[/red] {e}")
        raise typer.Exit(1) from None

    if not txs:
        console.print("No transactions found for this wallet.")
        return

    table = Table(title=f"Transaction history — {public_key[:16]}…", show_lines=True)
    table.add_column("Block", justify="right", style="dim", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Dir", justify="center", no_wrap=True)
    table.add_column("Amount", justify="right", style="cyan")
    table.add_column("Counterparty", style="dim")
    table.add_column("TX ID", style="dim", no_wrap=True)

    type_labels: dict[str, str] = {
        "Transfer": "Transfer",
        "FundProject": "Donate",
        "CreateProject": "New project",
        "Coinbase": "Mining reward",
    }

    for tx in txs:
        tx_type: str = tx.get("tx_type", "")
        from_addr: str | None = tx.get("from_address")
        to_addr: str | None = tx.get("to_address")
        amount = tx.get("amount")
        block = str(tx.get("block_height", "—"))
        tx_id: str = tx.get("tx_id", "")

        is_outgoing = from_addr == public_key
        direction = "[red]↑ out[/red]" if is_outgoing else "[green]↓ in[/green]"

        counterparty = to_addr if is_outgoing else from_addr
        counterparty_str = f"{counterparty[:16]}…" if counterparty else "—"

        amount_str = f"{amount}" if amount is not None else "—"
        label = type_labels.get(tx_type, tx_type)
        tx_short = f"{tx_id[:12]}…" if tx_id else "—"

        table.add_row(block, label, direction, amount_str, counterparty_str, tx_short)

    console.print(table)


# ==== PROJECT STATUS COMMAND ====


@project_app.command("status")
def project_status_cmd(
    project_id: str = typer.Argument(..., help="Project ID (proj_…)."),
    api: str = typer.Option(None, "--api", help="API URL. Defaults to saved config."),
) -> None:
    """
    Show full detail for a crowdfunding project.

    Displays goal vs raised progress, current status, and the five most
    recent backers.
    """
    api_url = api or get_api_url()

    try:
        p = get_project(api_url, project_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            console.print(f"[red]Project not found:[/red] {project_id}")
        elif e.response.status_code == 503:
            console.print("[red]Node unreachable — project data unavailable.[/red]")
        else:
            console.print(f"[red]API error:[/red] {e.response.text}")
        raise typer.Exit(1) from None
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to reach API:[/red] {e}")
        raise typer.Exit(1) from None

    goal: int = p.get("goal_amount", 0)
    raised: int = p.get("raised_amount", 0)
    pct = int(raised / goal * 100) if goal > 0 else 0
    bar_filled = pct // 5
    progress_bar = f"[{'█' * bar_filled}{'░' * (20 - bar_filled)}] {pct}%"

    status_colors: dict[str, str] = {
        "ACTIVE": "green",
        "SUCCESS": "bold green",
        "FAILED": "red",
        "CREATED": "yellow",
        "COMPLETED": "cyan",
    }
    status_str = p.get("status", "—")
    status_color = status_colors.get(status_str, "white")

    console.print(f"\n[bold]{p.get('name', project_id)}[/bold]")
    if p.get("description"):
        console.print(f"[dim]{p['description']}[/dim]")
    console.print(f"\nStatus:   [{status_color}]{status_str}[/{status_color}]")
    console.print(f"Goal:     [bold]{goal} coins[/bold]")
    console.print(f"Raised:   [bold cyan]{raised} coins[/bold cyan]  {progress_bar}")
    if p.get("creator_wallet"):
        console.print(f"Creator:  [dim]{p['creator_wallet'][:16]}…[/dim]")
    if p.get("deadline_timestamp"):
        deadline_dt = datetime.datetime.fromtimestamp(
            p["deadline_timestamp"], tz=datetime.UTC
        )
        console.print(f"Deadline: [dim]{deadline_dt.strftime('%Y-%m-%d')}[/dim]")

    backers: list[dict[str, object]] = p.get("recent_backers", [])
    if backers:
        console.print()
        btable = Table(title="Recent backers", show_lines=False, box=None)
        btable.add_column("Wallet", style="dim")
        btable.add_column("Amount", justify="right", style="cyan")
        btable.add_column("When", style="dim")
        for b in backers:
            addr = str(b.get("from_address", ""))
            amt = str(b.get("amount", "—"))
            ts = b.get("timestamp")
            when = (
                datetime.datetime.fromtimestamp(int(str(ts)), tz=datetime.UTC).strftime(
                    "%Y-%m-%d %H:%M"
                )
                if ts is not None
                else "—"
            )
            btable.add_row(f"{addr[:16]}…" if addr else "—", amt, when)
        console.print(btable)
    else:
        console.print("\n[dim]No backers yet.[/dim]")


# ==== LOGOUT COMMAND ====


@app.command("logout")
def logout_cmd() -> None:
    """
    Clear stored API tokens (log out of the BlockKick API).

    Does not deselect your wallet or clear your session key — only removes
    the JWT tokens saved by 'blockkick login'.
    """
    token = get_api_access_token()

    if not token:
        console.print("Not logged in.")
        return

    clear_api_tokens()
    console.print("[green]Logged out.[/green]")
    console.print("[dim]Run: blockkick login to authenticate again.[/dim]")


if __name__ == "__main__":
    app()
