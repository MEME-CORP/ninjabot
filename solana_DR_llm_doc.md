```yaml
wallets:
  description: >
    **Wallet Creation and Import (solders)** – Use the `solders` library (integrated with `solana` SDK v0.31.0) for key management ([Importing Solana Mnemonics with Python - Stack Overflow](https://stackoverflow.com/questions/77668870/importing-solana-mnemonics-with-python#:~:text=The%20only%20useful%20Python%20Solana,library)). This ensures compatibility with the latest Solana API. To generate a new keypair (for the **mother** or a **child** wallet), call `Keypair()` or `Keypair.generate()`. For importing an existing wallet, load the secret key bytes or base58 string. The `solders.keypair.Keypair` class provides `from_bytes()` and `from_base58_string()` for this purpose ([BOT GOAL | PDF | Cryptocurrency | Software](https://www.scribd.com/document/830207582/BOT-GOAL#:~:text=wallet%20%3D%20Keypair)) ([Transfer Solana using Solders for Python - Solana Stack Exchange](https://solana.stackexchange.com/questions/6190/transfer-solana-using-solders-for-python#:~:text=sender%20%3D%20%20Keypair)). Each `Keypair` contains a private key and can derive its public key via `.pubkey()`. Store secret keys securely (e.g., in environment variables or a vault) and never expose them in code. Optionally, for **HD wallets** (BIP-44 mnemonics), derive a 32-byte seed using a library like `bip_utils`, then use `Keypair.from_seed(seed)` ([Importing Solana Mnemonics with Python - Stack Overflow](https://stackoverflow.com/questions/77668870/importing-solana-mnemonics-with-python#:~:text=,ie)) to generate a deterministic keypair. 
   
    *Packages*: `solders` for `Keypair` and `Pubkey`; `base58` (if needed for decoding keys). The Solana SDK uses `solders` types internally for keys and signatures to avoid deprecated `solana` legacy key classes ([Importing Solana Mnemonics with Python - Stack Overflow](https://stackoverflow.com/questions/77668870/importing-solana-mnemonics-with-python#:~:text=The%20only%20useful%20Python%20Solana,library)).
  code: |
    ## Example: Creating and Importing Wallets
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey

    # Generate a new random keypair (e.g., for mother or child wallet)
    mother_wallet = Keypair()        # same as Keypair.generate()
    print("Mother wallet address:", str(mother_wallet.pubkey()))

    # Generate multiple child wallets (e.g., 3 child accounts)
    child_wallets = [Keypair() for _ in range(3)]
    for i, child in enumerate(child_wallets, start=1):
        print(f"Child {i} address: {child.pubkey()}")

    # Import an existing wallet from a 64-byte secret key (for example, stored securely)
    import base58
    secret_key_b58 = "<BASE58_SECRET_KEY>"  # e.g., from Phantom export or env var
    secret_key_bytes = base58.b58decode(secret_key_b58)
    imported_wallet = Keypair.from_bytes(secret_key_bytes)
    print("Imported wallet address:", imported_wallet.pubkey())

    # Alternatively, import directly from a base58 string:
    wallet2 = Keypair.from_base58_string(secret_key_b58)
    assert wallet2.pubkey() == imported_wallet.pubkey()

    # (Optional) Derive from mnemonic using bip_utils (not part of solana SDK):
    # seed_bytes = Bip39SeedGenerator(mnemonic_phrase).Generate()[:32]
    # hd_wallet = Keypair.from_seed(seed_bytes)
    # print("HD derived wallet:", hd_wallet.pubkey())
transfers:
  description: >
    **SPL Token Transfers** – To simulate trading volume, the bot will orchestrate SPL token transfers among the **mother** and **child** wallets. First, ensure each wallet has an **associated token account** for the SPL token of interest. The Solana SPL Token program requires a token account (ATA) for each wallet-mint pair. Use the `spl.token` library (installed with `solana`) to create and manage these accounts. For example, `Token.create_associated_token_account(owner_pubkey)` will create the ATA for a given owner (if it doesn't exist) using the mother wallet as fee payer. You should initialize a `Token` client with the token mint address, the token program ID, and a payer keypair. Typically, the **mother wallet** is used as the payer for account creation and possibly as the mint authority for distributing tokens. 

    Once token accounts are set up, transfers can be made. You can use high-level methods like `Token.transfer(...)` which will build and send the transaction for you ([Client - Solana.py](https://michaelhly.com/solana-py/spl/token/client/#:~:text=def%20transfer,SendTransactionResp)) ([Client - Solana.py](https://michaelhly.com/solana-py/spl/token/client/#:~:text=opts_to_use%20%3D%20TxOpts%28preflight_commitment%3Dself,amount%2C%20multi_signers%2C%20opts_to_use%2C%20recent_blockhash_to_use)). This method needs the source token account, destination token account, the owner of the source (as a `Keypair` for signing), and the amount (in the token’s smallest units). It returns a transaction signature upon success. Under the hood, it constructs a transaction with a single SPL token **Transfer** instruction and signs it with the provided owner keypair, then sends it via the RPC client. 

    Ensure the source wallet has sufficient token balance and the source account’s owner keypair signs the transaction. By default, the Solana Python SDK will use a recent blockhash and confirm the transaction (unless configured otherwise). The example below demonstrates connecting to a Solana cluster, creating associated token accounts for child wallets, and transferring tokens from the mother’s account to a child’s account. 

    *Packages*: `solana.rpc.api.Client` for RPC connection; `spl.token.client.Token` for token operations (account creation, transfer); `spl.token.constants` for `TOKEN_PROGRAM_ID`; `solders.pubkey.Pubkey` for addresses.
  code: |
    ## Example: Setting up Token Accounts and Transferring SPL Tokens
    from solana.rpc.api import Client
    from spl.token.client import Token
    from spl.token.constants import TOKEN_PROGRAM_ID
    from solders.pubkey import Pubkey

    # Connect to Solana network (devnet for testing, or mainnet-beta for production)
    client = Client("https://api.devnet.solana.com")
    # Assume we have the mother_wallet Keypair from before, and a token mint address:
    mother = mother_wallet  # (Keypair from previous section)
    mint_address = Pubkey.from_string("<SPL_TOKEN_MINT_ADDRESS>")

    # Initialize Token client for our SPL token
    token = Token(conn=client, pubkey=mint_address, program_id=TOKEN_PROGRAM_ID, payer=mother)

    # Create associated token accounts for each child (if not already existent)
    child_accounts = {}
    for i, child in enumerate(child_wallets, start=1):
        ata = token.create_associated_token_account(child.pubkey())  # create ATA for child
        child_accounts[child.pubkey()] = ata
        print(f"Created child {i} token account:", ata)

    # Mother wallet's associated token account (source of tokens)
    mother_ata = token.create_associated_token_account(mother.pubkey()) 
    # (If the ATA already exists, this will return the address without error)

    # Mint or supply tokens to the mother account if required (optional, if mother is mint authority):
    # token.mint_to(mother_ata, mother, amount=100_0000_0000)  # example to mint tokens to mother_ata

    # Transfer tokens from mother to a child (simulate a trade or distribution)
    dest_child = child_wallets[0]
    dest_child_ata = child_accounts[dest_child.pubkey()]
    transfer_amount = 1_000_000  # e.g., 1.000000 tokens (if mint has 6 decimals)
    result = token.transfer(
        source=mother_ata,
        dest=dest_child_ata,
        owner=mother,            # mother is the owner of source account
        amount=transfer_amount
    )
    # The result contains the transaction signature
    print("Transfer transaction signature:", result)
fees:
  description: >
    **Implementing a 0.1% Transfer Fee** – The bot charges a 0.1% fee on every token transfer, directing this fee to the central **mother wallet**. This can be achieved by splitting each transfer into two instructions within a single transaction: one transferring 99.9% of the amount to the intended recipient, and another transferring the remaining 0.1% to the mother wallet’s account. By combining these in one atomic transaction, the fee collection is guaranteed whenever a transfer occurs.

    To calculate the fee, compute `fee_amount = floor(total_amount * 0.001)`. Use integer arithmetic in terms of the token’s smallest unit (e.g., if the token has 6 decimal places, amount is in millionths). The main transfer amount will be `transfer_amount = total_amount - fee_amount`. In code, ensure both the fee and transfer instructions use the same source account and owner signer. The **source wallet’s keypair** will sign for both instructions (since it authorizes debits from the source token account). The fee instruction’s destination is the mother wallet’s token account.

    Using the lower-level `solders` transaction API, we can construct a custom transaction with multiple instructions. Below, we manually build a transaction for a child wallet sending tokens to another child (or to any target) while paying a fee to the mother. We use `spl.token.instructions.transfer` to create each instruction, then add them to a `Transaction`. Finally, we sign the transaction with the source wallet’s key and send it. (The `Token.transfer` method is high-level and sends immediately; for multiple instructions, manual assembly is needed.) Note that in Solana Python v0.31+, `Transaction` and `Message` are from the `solders` library. We fetch a recent blockhash for the transaction and then send it. 

    *Packages*: `spl.token.instructions` for crafting transfer instructions; `solders.transaction.Transaction` and `solders.message.Message` for assembling multi-instruction transactions; `solana.rpc.api.Client` for sending. This approach reflects current best practices, as older approaches of using `solana.transaction.Transaction` are replaced by solders types ([BOT GOAL | PDF | Cryptocurrency | Software](https://www.scribd.com/document/830207582/BOT-GOAL#:~:text=4,no)).
  code: |
    ## Example: Transfer with 0.1% Fee (two instructions in one transaction)
    from spl.token.instructions import transfer as token_transfer, TransferParams
    from solders.transaction import Transaction
    from solders.message import Message
    from solders.hash import Hash

    # Assume source is a child wallet sending tokens, and destination is another child
    source_wallet = child_wallets[0]           # Keypair of source (payer of fee and transfer)
    dest_wallet = child_wallets[1]             # Recipient wallet
    mint = mint_address                        # Pubkey of the token mint (from above)
    source_ata = child_accounts[source_wallet.pubkey()]  # source's token account
    dest_ata = child_accounts[dest_wallet.pubkey()]      # destination's token account
    mother_ata = mother_ata                    # mother's token account (fee receiver)

    total_amount = 500_000  # e.g., 0.5 token in base units (assuming 6 decimals)
    fee_amount = total_amount // 1000  # 0.1% fee (integer division)
    transfer_amount = total_amount - fee_amount

    # Create SPL Token transfer instructions
    ix_transfer = token_transfer(TransferParams(
        program_id=TOKEN_PROGRAM_ID,
        source=source_ata,
        dest=dest_ata,
        owner=source_wallet.pubkey(),
        amount=transfer_amount
    ))
    ix_fee = token_transfer(TransferParams(
        program_id=TOKEN_PROGRAM_ID,
        source=source_ata,
        dest=mother_ata,
        owner=source_wallet.pubkey(),
        amount=fee_amount
    ))

    # Prepare and send the transaction with both instructions
    # Fetch a recent blockhash for the transaction
    latest_blockhash = client.get_latest_blockhash().value.blockhash
    # Construct the message and transaction
    message = Message(instructions=[ix_transfer, ix_fee], payer=source_wallet.pubkey())
    # Convert blockhash to Hash object if needed (solders Hash)
    recent_hash_obj = Hash.from_string(str(latest_blockhash))
    transaction = Transaction(from_keypairs=[source_wallet], message=message, recent_blockhash=recent_hash_obj)
    # Sign the transaction (source_wallet signs as it's the fee payer and source owner)
    transaction.sign([source_wallet], recent_hash_obj)
    # Send the transaction to the network
    sig = client.send_transaction(transaction)
    print("Combined transfer+fee tx signature:", sig)
    # Note: The returned `sig` is a solders `Signature` object. Use str(sig) to get the base58 signature string if needed.
transactions:
  description: >
    **Transaction Confirmation and Reliability** – After sending a transaction, it's crucial to confirm it and handle any potential errors. The Solana RPC can automatically confirm transactions if `TxOpts.skip_confirmation=False` (the default). For example, the `Token.transfer` call waits for confirmation by default and returns once the transaction is confirmed at the specified commitment. If you need manual confirmation, use `Client.confirm_transaction(signature, commitment)` to poll the cluster until the given commitment (e.g., `"confirmed"` or `"finalized"`) is reached. This returns a response indicating the result (and error if any) of the transaction. 

    Network fees on Solana are typically **0.000005 SOL per signature** (5,000 lamports) ([API Client - Solana.py](https://michaelhly.com/solana-py/rpc/api/#solana.rpc.api.Client.send_transaction#:~:text=%3E%3E%3E%20solana_client.get_fee_for_message%28msg%29.value%20,5000)). You can estimate fees for a prospective transaction using `Client.get_fee_for_message(message)` which returns the exact lamport cost for that transaction message ([API Client - Solana.py](https://michaelhly.com/solana-py/rpc/api/#solana.rpc.api.Client.send_transaction#:~:text=)). In most simple cases with one signer, this will be 5000 lamports. Ensure the fee payer (usually the first signer or the one set as `payer` in the `Message`) has enough SOL to cover these fees, especially when orchestrating many transfers.

    **Retrying failed transactions** – The bot should handle transient failures. A common failure is **expired blockhash** (if the transaction wasn’t processed in time or the blockhash is too old). In such cases, the RPC will return an error (e.g., "blockhash not found" or similar expiration message). To handle this, catch exceptions (e.g., `solana.rpc.core.RPCException`) from `send_transaction`. If the error indicates an expired blockhash, fetch a new `latest_blockhash`, update the transaction’s `recent_blockhash`, re-sign, and resend. The example code below illustrates a retry loop for blockhash expiration. It’s also good practice to set `TxOpts(max_retries=N)` when sending to let the RPC server retry broadcasting, and `preflight_commitment="processed"` for faster initial simulation.

    Additionally, ensure **idempotency** or uniqueness if resending the same transaction (Solana will reject duplicate signatures within a short time). You might need to regenerate a new transaction (with a new blockhash or even a no-op tweak) if the original could have been partially processed. Monitoring the transaction signature status via `get_signature_statuses` or `get_transaction` can also inform if a retry is needed or if the tx actually landed.

    **Commitment levels** – Use appropriate commitment when querying or confirming (e.g., "confirmed" for speed, "finalized" for highest assurance). For high reliability in a production environment, you might use a WebSocket subscription to get real-time confirmations or use services like QuikNode/Alchemy with auto-retry logic. Always handle exceptions gracefully and log the outcome of each transaction. 

    *Packages*: `solana.rpc.api.Client` for sending and confirmation; `solana.rpc.core.RPCException` for error handling. The logic below demonstrates confirming a transaction and a simple retry mechanism for blockhash expiration.
  code: |
    ## Example: Confirming a transaction and retry on failure
    from solana.rpc.core import RPCException
    from solana.rpc.types import TxOpts

    # Send a transaction (for example, using the one from the fee section)
    try:
        # Here we use send_transaction; by default it waits for confirmation (skip_confirmation=False)
        signature = client.send_transaction(transaction, opts=TxOpts(preflight_commitment="confirmed"))
        print("Transaction sent, signature:", str(signature))
        # Explicit confirmation (if needed):
        confirmation = client.confirm_transaction(signature, commitment="confirmed")
        print("Transaction confirmation status:", confirmation.value)
    except RPCException as e:
        print("Transaction send error:", e)
        # If blockhash expired or not found, retry with new blockhash
        if "blockhash" in str(e) or "expired" in str(e):
            print("Blockhash expired, retrying...")
            # Refresh blockhash and retry once
            latest_blockhash = client.get_latest_blockhash().value.blockhash
            # Update transaction with new blockhash and resign
            new_hash_obj = Hash.from_string(str(latest_blockhash))
            transaction.recent_blockhash = new_hash_obj
            transaction.sign([source_wallet], new_hash_obj)
            try:
                signature = client.send_transaction(transaction, opts=TxOpts(preflight_commitment="confirmed"))
                client.confirm_transaction(signature, commitment="confirmed")
                print("Resend successful, signature:", str(signature))
            except Exception as e2:
                print("Retry failed:", e2)
        else:
            # Other errors (e.g., simulation error, node issue)
            raise

    # Estimate fees for a new transaction (for information purposes)
    # Construct a Message for a prospective transaction (using the same instructions as before)
    msg = Message(instructions=[ix_transfer, ix_fee], payer=source_wallet.pubkey())
    fee_response = client.get_fee_for_message(msg)
    print("Estimated fee (lamports):", fee_response.value)
optional_swaps:
  description: >
    **Optional: Token Swap/Buy/Sell Operations** – In addition to direct token transfers, the bot could simulate volume via token swaps (trades) on Solana’s decentralized exchanges. This involves swapping the SPL token with another token (e.g., SOL or USDC) through a DEX program. While the Solana Python SDK doesn’t have built-in high-level swap functions, you can integrate with Solana DeFi protocols or use aggregator APIs:

    - *Jupiter API/SDK*: Jupiter is a Solana token swap aggregator. The **Jupiter Python SDK** (e.g., `jupiter-python-sdk`) or the REST API can provide a ready-to-execute swap transaction for a given input/output token pair. For example, you can request a quote and transaction from Jupiter for swapping a certain amount of your token to another token ([Transfer Solana using Solders for Python - Solana Stack Exchange](https://solana.stackexchange.com/questions/6190/transfer-solana-using-solders-for-python#:~:text=,outputMint%3D%7Boutput_token_address%7D%26amount%3D%7Bint%28amount%20%2A%2010%2A%2A9%29%7D%26slippageBps%3D50)). The API returns a base64 encoded `swapTransaction` that you can decode and sign with your Keypair (as the payer and source owner) before sending. Ensure to use `solders.transaction.VersionedTransaction` for Versioned transactions if Jupiter returns one, and sign it with the appropriate key(s).

    - *Serum DEX (PySerum)*: For more control, you can interact with Serum via the `pyserum` library to place orders on an orderbook. This requires creating Serum market accounts, placing bid/ask orders, etc., which is more complex but simulates realistic trading. 

    - *Anchorpy*: If an on-chain program (like the SPL Token Swap program or a liquidity pool) has an Anchor interface, you could use `anchorpy` to load the IDL and perform swaps. However, for most use cases, Jupiter’s aggregated swap is the simplest route.

    **Example (Jupiter swap via REST)**: The bot fetches a quote from Jupiter’s `/quote` endpoint for the desired swap pair, then calls the `/swap` endpoint to get a transaction. The transaction is then decoded and sent through the Solana client. (Pseudocode below illustrates this process.) Always handle the possibility of price impact and slippage; Jupiter’s API allows specifying slippage basis points in the request. Also, maintain up-to-date compatibility between the Solana SDK and Jupiter (as seen by issues when deserializing Jupiter transactions if versions mismatch ([BOT GOAL | PDF | Cryptocurrency | Software](https://www.scribd.com/document/830207582/BOT-GOAL#:~:text=signal,Current%20Code))).

    *Packages*: `requests` for HTTP API calls (if using Jupiter REST), `solders.transaction.VersionedTransaction` for handling the returned swap transactions, or `jupiter_python_sdk` for a more direct Python integration.
  code: |
    ## Example: Using Jupiter API to perform a token swap (pseudo-code)
    import requests, base64
    from solders.transaction import VersionedTransaction

    input_mint = str(mint_address)        # Token you want to swap from (SPL token)
    output_mint = str(Pubkey.from_string("So11111111111111111111111111111111111111112"))  # e.g., SOL (wrapped SOL mint)
    swap_amount = 1000000                # amount in smallest units to swap
    slippage_bps = 100                   # 1% slippage tolerance

    # 1. Get a swap route quote from Jupiter
    quote_url = (f"https://quote-api.jup.ag/v6/quote?inputMint={input_mint}"
                 f"&outputMint={output_mint}&amount={swap_amount}&slippageBps={slippage_bps}")
    quote_resp = requests.get(quote_url).json()
    routes = quote_resp.get("data", [])
    if not routes:
        raise Exception("No swap route found")
    best_route = routes[0]

    # 2. Request swap transaction for the chosen route
    swap_req = {
        "route": best_route,
        "userPublicKey": str(source_wallet.pubkey())  # wallet executing the swap
    }
    swap_resp = requests.post("https://quote-api.jup.ag/v6/swap", json=swap_req).json()
    swap_tx_b64 = swap_resp.get("swapTransaction")
    swap_tx_bytes = base64.b64decode(swap_tx_b64)

    # 3. Deserialize and sign the swap transaction
    swap_tx = VersionedTransaction.from_bytes(swap_tx_bytes)
    swap_tx.sign([source_wallet])  # sign with the source wallet (must have the input tokens)
    # 4. Send the signed transaction
    swap_sig = client.send_transaction(swap_tx, opts=TxOpts(preflight_commitment="confirmed"))
    print("Swap transaction signature:", swap_sig)
``` 

