#!/usr/bin/env python
"""
Runner script for API integration tests.

This script provides a command-line interface to run the API integration tests.
"""

import os
import sys
import argparse
from pathlib import Path

def main():
    """Run tests with proper command-line arguments."""
    parser = argparse.ArgumentParser(description="Run API integration tests")
    parser.add_argument(
        "--phase", "-p", type=str, 
        help="Specific phase to test (e.g., '0.1', '0.2', '0.3', '0.5')"
    )
    args = parser.parse_args()
    
    # Make sure test_api_integration.py is executable
    test_script = Path("test_api_integration.py")
    if not test_script.exists():
        print(f"Error: Could not find {test_script}")
        sys.exit(1)
    
    # Make the script executable if it's not already
    test_script.chmod(test_script.stat().st_mode | 0o111)
    
    # Run the appropriate tests
    if args.phase:
        # Run a specific phase
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
    else:
        # Run all tests
        from test_api_integration import run_all_tests
        run_all_tests()

if __name__ == "__main__":
    main() 