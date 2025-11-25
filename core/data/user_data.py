import json
from pathlib import Path
from typing import Dict, Any


def load_user_data() -> Dict[str, Any]:
    project_root = Path(__file__).parent.parent.parent
    user_data_path = project_root / "seed" / "user_info.json"
    with open(user_data_path) as f:
        user_data = json.load(f)
    return user_data