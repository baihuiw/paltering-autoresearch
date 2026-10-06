"""Load OPENROUTER_API_KEY from the git-ignored .env file in the repository root, unless the shell already set it.
The key is never printed or logged."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_key():
    if os.environ.get('OPENROUTER_API_KEY'):
        return True
    env = ROOT / '.env'
    if env.exists():
        for line in env.read_text().splitlines():
            name, _, value = line.partition('=')
            if name.strip() == 'OPENROUTER_API_KEY' and value.strip():
                os.environ['OPENROUTER_API_KEY'] = value.strip().strip('"').strip("'")
                return True
    return False
