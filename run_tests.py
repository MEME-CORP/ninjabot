#!/usr/bin/env python
"""
Runner script for API integration tests.

This script provides a command-line interface to run the API integration tests.
"""

import os
import sys
import argparse
import asyncio
from pathlib import Path

def main():
    """Run tests with proper command-line arguments."""
    parser = argparse.ArgumentParser(description="Run API integration tests")
    parser.add_argument(
        "--phase", "-p", type=str, 
        help="Specific phase to test (e.g., '0.1', '0.2', '0.3', '0.5')"
    )
    parser.add_argument(
        "--module", "-m", type=str,
        help="Specific test module to run (e.g., 'api', 'volume', 'fee', 'tx', 'strategy', 'private_key_fixes')"
    )
    parser.add_argument(
        "--all", "-a", action="store_true",
        help="Run all tests from all modules"
    )
    args = parser.parse_args()

    # If no arguments are provided, show help
    if not (args.phase or args.module or args.all):
        parser.print_help()
        sys.exit(1)
    
    # Make sure test scripts are executable
    test_scripts = [
        Path("test_api_integration.py"),
        Path("test_volume_service.py"),
        Path("test_fee_service.py"),
        Path("test_tx_service.py"),
        Path("test_strategy_service.py")
    ]
    
    for script in test_scripts:
        if script.exists():
            # Make the script executable if it's not already
            script.chmod(script.stat().st_mode | 0o111)
    
    # Run the appropriate tests
    if args.phase and not args.module:
        # Run a specific phase of API integration tests
        if args.phase not in ["0.1", "0.2", "0.3", "0.5"]:
            print(f"Error: Invalid phase '{args.phase}'. Valid phases are: 0.1, 0.2, 0.3, 0.5")
            sys.exit(1)
            
        # Import the test module
        from test_api_integration import (
            test_phase_0_1, test_phase_0_2, test_phase_0_3, test_phase_0_5
        )
        
        # Run the specified phase
        if args.phase == "0.1":
            test_phase_0_1()
        elif args.phase == "0.2":
            wallet_result = test_phase_0_2()
            if not wallet_result:
                sys.exit(1)
        elif args.phase == "0.3":
            if not test_phase_0_1():
                print("API connectivity test failed. Cannot proceed.")
                sys.exit(1)
                
            wallet_result = test_phase_0_2()
            if not wallet_result:
                print("Wallet lifecycle test failed. Cannot proceed.")
                sys.exit(1)
                
            mother_address, _ = wallet_result
            test_phase_0_3(mother_address)
        elif args.phase == "0.5":
            if not test_phase_0_1():
                print("API connectivity test failed. Cannot proceed.")
                sys.exit(1)
                
            wallet_result = test_phase_0_2()
            if not wallet_result:
                print("Wallet lifecycle test failed. Cannot proceed.")
                sys.exit(1)
                
            mother_address, children = wallet_result
            
            if not test_phase_0_3(mother_address):
                print("Balance polling test failed. Cannot proceed.")
                sys.exit(1)
                
            test_phase_0_5(mother_address, children)
    elif args.module:
        # Run a specific test module
        if args.module == "api":
            from test_api_integration import run_all_tests
            run_all_tests()
        elif args.module == "volume":
            from test_volume_service import run_all_tests
            run_all_tests()
        elif args.module == "fee":
            from test_fee_service import run_all_tests
            run_all_tests()
        elif args.module == "tx":
            from test_tx_service import run_all_tests
            asyncio.run(run_all_tests())
        elif args.module == "strategy":
            from test_strategy_service import run_all_tests
            run_all_tests()
        elif args.module == "private_key_fixes":
            from test_private_key_fixes import run_all_tests
            run_all_tests()
        else:
            print(f"Error: Invalid module '{args.module}'. Valid modules are: 'api', 'volume', 'fee', 'tx', 'strategy', 'private_key_fixes'")
            sys.exit(1)
    elif args.all:
        # Run all tests from all modules
        print("Running all tests from all modules...")
        
        # API integration tests
        try:
            from test_api_integration import run_all_tests as run_api_tests
            api_success = run_api_tests()
        except Exception as e:
            print(f"Error running API integration tests: {str(e)}")
            api_success = False
        
        # Volume service tests
        try:
            from test_volume_service import run_all_tests as run_volume_tests
            volume_success = run_volume_tests()
        except Exception as e:
            print(f"Error running volume service tests: {str(e)}")
            volume_success = False
        
        # Fee service tests
        try:
            from test_fee_service import run_all_tests as run_fee_tests
            fee_success = run_fee_tests()
        except Exception as e:
            print(f"Error running fee service tests: {str(e)}")
            fee_success = False
        
        # Transaction service tests
        try:
            from test_tx_service import run_all_tests as run_tx_tests
            tx_success = asyncio.run(run_tx_tests())
        except Exception as e:
            print(f"Error running transaction service tests: {str(e)}")
            tx_success = False
        
        # Strategy service tests
        try:
            from test_strategy_service import run_all_tests as run_strategy_tests
            strategy_success = run_strategy_tests()
        except Exception as e:
            print(f"Error running strategy service tests: {str(e)}")
            strategy_success = False
        
        # Private key fixes tests
        try:
            from test_private_key_fixes import run_all_tests as run_private_key_tests
            private_key_success = run_private_key_tests()
        except Exception as e:
            print(f"Error running private key fixes tests: {str(e)}")
            private_key_success = False
        
        # Print overall summary
        print("\n" + "=" * 80)
        print("  Overall Test Summary")
        print("=" * 80)
        print(f"API Integration Tests: {'✅ PASSED' if api_success else '❌ FAILED'}")
        print(f"Volume Service Tests: {'✅ PASSED' if volume_success else '❌ FAILED'}")
        print(f"Fee Service Tests: {'✅ PASSED' if fee_success else '❌ FAILED'}")
        print(f"Transaction Service Tests: {'✅ PASSED' if tx_success else '❌ FAILED'}")
        print(f"Strategy Service Tests: {'✅ PASSED' if strategy_success else '❌ FAILED'}")
        print(f"Private Key Fixes Tests: {'✅ PASSED' if private_key_success else '❌ FAILED'}")
        
        # Determine overall success
        overall_success = api_success and volume_success and fee_success and tx_success and strategy_success and private_key_success
        print(f"\nOverall Result: {'✅ PASSED' if overall_success else '❌ FAILED'}")
        
        # Exit with appropriate status code
        sys.exit(0 if overall_success else 1)
    else:
        # Run all API integration tests by default
        from test_api_integration import run_all_tests
        run_all_tests()

if __name__ == "__main__":
    main() 