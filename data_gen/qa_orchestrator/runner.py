import pytest
import sys
import os
from typing import List, Optional

class TestRunner:
    """
    A wrapper around pytest to run tests programmatically.
    """
    def __init__(self, default_args: Optional[List[str]] = None):
        self.default_args = default_args or []

    def run(self, args: Optional[List[str]] = None) -> int:
        """
        Run pytest with the given arguments.
        
        Args:
            args: List of arguments to pass to pytest.
            
        Returns:
            Exit code from pytest.
        """
        if os.getcwd() not in sys.path:
            sys.path.insert(0, os.getcwd())

        final_args = self.default_args + (args or [])
        print(f"Running pytest with args: {final_args}")
        return pytest.main(final_args)

    def run_tests_in_path(self, path: str, args: Optional[List[str]] = None) -> int:
        """
        Run tests in a specific path.
        """
        return self.run([path] + (args or []))
