from cryptography.fernet import Fernet
import json, os

class LocalHistory:
    def __init__(self, key_path="~/.dating_wellbeing/key.bin"):
        self.key_path = os.path.expanduser(key_path)
        if not os.path.exists(self.key_path):
            self.key = Fernet.generate_key()
            with open(self.key_path, "wb") as f: f.write(self.key)
        else:
            with open(self.key_path, "rb") as f: self.key = f.read()
        self.cipher = Fernet(self.key)

    def save_analysis(self, data: dict):
        enc = self.cipher.encrypt(json.dumps(data).encode())
        hist_path = os.path.expanduser("~/.dating_wellbeing/history.enc")
        with open(hist_path, "ab") as f:
            f.write(enc + b"\n")
