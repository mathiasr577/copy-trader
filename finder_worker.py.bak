import time
import subprocess
import sys

if __name__ == "__main__":
    print("[worker] Wallet finder iniciado — corriendo cada 15 minutos")
    while True:
        print("[worker] Corriendo wallet_finder.py...")
        subprocess.run([sys.executable, "wallet_finder.py"])
        print("[worker] Esperando 15 minutos...")
        time.sleep(900)