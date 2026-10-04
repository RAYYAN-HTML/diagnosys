import argparse
import sys

from diagnosys.cli.commands import setup_commands
from diagnosys.config.logging import configure_logging

def main():
    parser = argparse.ArgumentParser(
        prog="diagnosys",
        description="Diagnosys: Local-first PC and Internet health diagnostic agent."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    setup_commands(parser)
    
    args = parser.parse_args()
    
    configure_logging(debug=args.debug)
    
    if hasattr(args, "func"):
        sys.exit(args.func(args))
    else:
        parser.print_help()
        sys.exit(0)

if __name__ == "__main__":
    main()
