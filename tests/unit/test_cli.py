import pytest
from unittest.mock import patch
import sys

from diagnosys.cli.main import main

def test_cli_help(capsys):
    """Test that the CLI can print help and exit cleanly."""
    with patch.object(sys, 'argv', ['diagnosys', '--help']):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        
    captured = capsys.readouterr()
    assert "Diagnosys: Local-first PC and Internet health diagnostic agent." in captured.out

def test_cli_no_args(capsys):
    """Test that the CLI prints help and exits when no args are passed."""
    with patch.object(sys, 'argv', ['diagnosys']):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        
    captured = capsys.readouterr()
    assert "usage:" in captured.out
