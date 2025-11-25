
import json, os

STATE_PATH = os.getenv("STATE_PATH", "state.json")

def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH,"r") as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    with open(STATE_PATH,"w") as f:
        json.dump(state,f)
