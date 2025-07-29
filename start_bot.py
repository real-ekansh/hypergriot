#!/usr/bin/env python3
"""
HyperGriot Bot Startup Script
Handles environment loading and bot initialization
"""

import os
import sys
from dotenv import load_dotenv

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    # Check required environment variables
    required_vars = ['BOT_TOKEN', 'OWNER_ID']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("ERROR: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease set these variables in your .env file or environment")
        print("See .env.example for reference")
        sys.exit(1)
    
    # Display configuration
    print("HyperGriot Bot Configuration:")
    print(f"  Owner ID: {os.getenv('OWNER_ID')}")
    print(f"  Database: {'MongoDB' if os.getenv('USE_MONGODB', '').lower() == 'true' else 'SQLite'}")
    print(f"  Modules Directory: {'modules/' if os.path.exists('modules') else 'modules/ (not found)'}")
    
    # Import and run the main bot
    try:
        print("\nStarting HyperGriot Bot...")
        import hypergriot_bot
    except ImportError as e:
        print(f"ERROR: Failed to import bot module: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nBot stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: Bot crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
