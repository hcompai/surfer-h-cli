#!/usr/bin/env python3
"""
Environment loader for bash scripts.
Loads .env file and exports specified environment variables for bash eval.
"""

import os
import sys


def main():
    """Load environment and export specified variables."""
    # Parse command line arguments for required variables
    if len(sys.argv) < 2:
        print("Usage: load_env.py VAR1 VAR2 VAR3...", file=sys.stderr)
        sys.exit(1)

    required_vars = sys.argv[1:]

    # Load .env file
    try:
        from dotenv import load_dotenv

        load_dotenv()
        print("📄 Environment loaded from .env file", file=sys.stderr)
    except ImportError:
        print("⚠️  Warning: python-dotenv not available", file=sys.stderr)
    except Exception as e:
        print(f"⚠️  Error loading .env: {e}", file=sys.stderr)

    missing_vars = []

    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f'export {var}="{value}"')
            print(f'echo "   ✅ {var}: {value}"', file=sys.stderr)
        else:
            missing_vars.append(var)

    if missing_vars:
        print('echo "❌ Missing required environment variables:"', file=sys.stderr)
        for var in missing_vars:
            print(f'echo "   - {var}"', file=sys.stderr)
        print('echo "Please set these variables in your .env file."', file=sys.stderr)
        print('echo ""', file=sys.stderr)
        print("exit 1")
        sys.exit(1)

    print('echo "✅ All required environment variables are set"', file=sys.stderr)


if __name__ == "__main__":
    main()
