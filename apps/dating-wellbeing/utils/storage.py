from cryptography.fernet import Fernet
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dw_paths import app_data

class LocalHistory:
    def __init__(self, key_path=None):
        self.key_path = str(key_path) if key_path else str(app_data() / "key.bin")
        os.makedirs(os.path.dirname(self.key_path), exist_ok=True)
        if not os.path.exists(self.key_path):
            self.key = Fernet.generate_key()
            with open(self.key_path, "wb") as f: f.write(self.key)
        else:
            with open(self.key_path, "rb") as f: self.key = f.read()
        self.cipher = Fernet(self.key)

    def save_analysis(self, data: dict):
        enc = self.cipher.encrypt(json.dumps(data).encode())
        hist_path = str(app_data() / "history.enc")
        os.makedirs(os.path.dirname(hist_path), exist_ok=True)
        with open(hist_path, "ab") as f:
            f.write(enc + b"\n")
