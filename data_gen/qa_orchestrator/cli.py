import sys
from .runner import TestRunner

def main():
    """
    CLI entry point for test-orchestrator.
    Passes arguments directly to the pytest wrapper.
    """
    runner = TestRunner()
    # sys.argv[0] is the script name, so we pass the rest
    sys.exit(runner.run(sys.argv[1:]))

if __name__ == "__main__":
    main()
