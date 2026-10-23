"""Show the existing Concierge native Fetch receive address, never its key."""
import os
from pathlib import Path


def recipient_address(seed: str) -> str:
    from cosmpy.aerial.wallet import LocalWallet,PrivateKey
    from uagents.config import LEDGER_PREFIX
    from uagents_core.identity import derive_key_from_seed
    wallet=LocalWallet(PrivateKey(derive_key_from_seed(seed+':concierge',LEDGER_PREFIX,0)),prefix=LEDGER_PREFIX)
    return str(wallet.address())


def main():
    from dotenv import load_dotenv
    load_dotenv()
    seed=os.getenv('SERVICESETU_SEED')
    if not seed:
        path=Path('data/agent-seed')
        if path.is_file():seed=path.read_text().strip()
    if not seed:raise SystemExit('Existing ServiceSetu seed not found; configure it privately before deriving the receive address')
    address=recipient_address(seed)
    if not address.startswith('fetch1'):raise SystemExit('Derived recipient is not a native Fetch wallet address')
    print('ServiceSetu Concierge native Fetch testnet receive wallet:',address)
    print('This fetch1 address is separate from the public agent1 messaging address. No private key or seed was printed.')


if __name__=='__main__':main()
