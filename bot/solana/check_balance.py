"""
Utility script to check wallet balances on Solana.
"""

import argparse
import asyncio
from solana.rpc.api import Client
from loguru import logger

async def check_sol_balance(wallet_address: str, network: str = "devnet"):
    """Check SOL balance of a wallet."""
    rpc_url = "https://api.devnet.solana.com" if network == "devnet" else "https://api.mainnet-beta.solana.com"
    client = Client(rpc_url)
    
    try:
        response = client.get_balance(wallet_address)
        if "result" in response and "value" in response["result"]:
            lamports = response["result"]["value"]
            sol = lamports / 1e9
            print(f"Wallet: {wallet_address}")
            print(f"SOL Balance: {sol:.9f}")
            return sol
        else:
            print(f"Error getting balance: {response}")
            return None
    except Exception as e:
        print(f"Error checking balance: {str(e)}")
        return None

async def check_token_balance(wallet_address: str, token_mint: str, network: str = "devnet"):
    """Check SPL token balance of a wallet."""
    rpc_url = "https://api.devnet.solana.com" if network == "devnet" else "https://api.mainnet-beta.solana.com"
    client = Client(rpc_url)
    
    try:
        # Get token accounts
        response = client.get_token_accounts_by_owner(
            wallet_address,
            {"mint": token_mint}
        )
        
        if "result" in response and "value" in response["result"] and response["result"]["value"]:
            token_account = response["result"]["value"][0]["pubkey"]
            
            # Get token balance
            balance_response = client.get_token_account_balance(token_account)
            
            if "result" in balance_response and "value" in balance_response["result"]:
                amount = balance_response["result"]["value"]["amount"]
                decimals = balance_response["result"]["value"]["decimals"]
                
                token_amount = int(amount) / (10 ** decimals)
                
                print(f"Wallet: {wallet_address}")
                print(f"Token Mint: {token_mint}")
                print(f"Token Account: {token_account}")
                print(f"Token Balance: {token_amount}")
                return token_amount
            else:
                print(f"Error getting token balance: {balance_response}")
                return None
        else:
            print(f"No token account found for wallet {wallet_address} and token {token_mint}")
            return None
    except Exception as e:
        print(f"Error checking token balance: {str(e)}")
        return None

async def main():
    parser = argparse.ArgumentParser(description="Check wallet balances on Solana")
    parser.add_argument("wallet", type=str, help="Wallet address to check")
    parser.add_argument("--token", type=str, default=None, help="Token mint address (optional)")
    parser.add_argument("--network", type=str, default="devnet", choices=["devnet", "mainnet"], help="Network to use")
    
    args = parser.parse_args()
    
    if args.token:
        await check_token_balance(args.wallet, args.token, args.network)
    else:
        await check_sol_balance(args.wallet, args.network)

if __name__ == "__main__":
    asyncio.run(main()) 