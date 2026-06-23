import os
from dotenv import load_dotenv

load_dotenv()


def get_env_var(var_name: str):
    env_var = os.environ.get(var_name)
    if env_var is None:
        raise ValueError("No key exists.")
    return env_var


onyx_url = get_env_var("ONYX_URL")
user_agent = get_env_var("USER_AGENT")
