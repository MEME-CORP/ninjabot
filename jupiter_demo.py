#!/usr/bin/env python3
"""
Jupiter DEX Integration Demo
===========================

Demonstrates how to use the integrated Jupiter swap functionality 
in the ApiClient class.

This script shows the complete workflow:
1. Get supported tokens
2. Get a swap quote  
3. Execute the swap
4. Verify results
"""

import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))

from bot.api.api_client import ApiClient
from loguru import logger

def main():
    """Demonstrate Jupiter DEX integration functionality."""
    
    print("🚀 Jupiter DEX Integration Demo")
    print("=" * 40)
    
    # Initialize the API client in mock mode for demonstration
    client = ApiClient()
    client.use_mock = True  # Using mock mode for safe demonstration
    
    try:
        # Step 1: Get supported tokens
        print("\n📋 Step 1: Getting supported tokens...")
        tokens_response = client.get_jupiter_supported_tokens()
        tokens = tokens_response["tokens"]
        
        print(f"✅ Found {len(tokens)} supported tokens:")
        for symbol, address in list(tokens.items())[:5]:  # Show first 5
            print(f"   {symbol}: {address[:8]}...{address[-8:]}")
        
        # Step 2: Get a swap quote
        print("\n💰 Step 2: Getting swap quote...")
        quote_response = client.get_jupiter_quote(
            input_mint="SOL",
            output_mint="USDC",
            amount=1000000000,  # 1 SOL in lamports
            slippage_bps=50     # 0.5% slippage tolerance
        )
        
        quote_data = quote_response["quoteResponse"]
        formatted_info = quote_data["_formattedInfo"]
        
        print(f"✅ Quote retrieved successfully:")
        print(f"   Input: {formatted_info['inputAmount']} {formatted_info['inputToken']}")
        print(f"   Output: {formatted_info['outputAmount']} {formatted_info['outputToken']}")
        print(f"   Price Impact: {formatted_info['priceImpactPct']}%")
        print(f"   Route Steps: {formatted_info['routeSteps']}")
        
        # Step 3: Execute the swap
        print("\n🔄 Step 3: Executing swap...")
        swap_result = client.execute_jupiter_swap(
            user_wallet_private_key="demo_private_key_mock_only",
            quote_response=quote_response,
            wrap_and_unwrap_sol=True,
            collect_fees=True,
            verify_swap=True
        )
        
        print(f"✅ Swap executed successfully:")
        print(f"   Transaction ID: {swap_result['transactionId']}")
        print(f"   Status: {swap_result['status']}")
        print(f"   Execution Time: {swap_result['executionTime']}s")
        
        # Step 4: Check fee collection
        fee_collection = swap_result.get("feeCollection")
        if fee_collection:
            print(f"   Fee Collection: {fee_collection['status']}")
            print(f"   Fee Amount: {fee_collection['feeAmount']} {fee_collection['feeTokenMint']}")
        
        print(f"   New SOL Balance: {swap_result['newBalanceSol']} SOL")
        print(f"   Verified: {swap_result['verified']}")
        
        print("\n🎉 Jupiter integration demo completed successfully!")
        print("\nℹ️  This demo used mock mode. In production:")
        print("   - Set client.use_mock = False")
        print("   - Use real wallet private keys")
        print("   - Connect to actual Jupiter API endpoints")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    # Set environment variable for demo
    os.environ["BOT_TOKEN"] = "demo_token_for_jupiter_integration"
    exit(main())