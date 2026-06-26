#!/usr/bin/env python3

import sys
import json
import random
import string
import socket
import os
import re
from enum import Enum
from typing import Optional, Tuple, List, Any

# ==================== CONFIGURATION ====================
PORT = 4444
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
SOCKET_TIMEOUT = 10.0
HISTORY_SIZE = 10
USER_ID_LEN = 32
TOKEN_LEN = 16

random = random.SystemRandom()


def debug_log(msg: str, level: str = "INFO") -> None:
    """Вывод отладочной информации с уровнями"""
    if DEBUG:
        colors = {
            "INFO": "\033[94m",    # Синий
            "GOOD": "\033[92m",    # Зеленый
            "WARN": "\033[93m",    # Желтый
            "ERROR": "\033[91m",   # Красный
            "RESET": "\033[0m"     # Сброс
        }
        color = colors.get(level, colors["INFO"])
        print(f"{color}[{level}]{colors['RESET']} {msg}", file=sys.stderr, flush=True)


# ==================== DATA GENERATORS ====================
def load_replica_sentences() -> List[str]:
    """Загрузка предложений из Replica.json"""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        replica_path = os.path.join(script_dir, "Replica.json")
        with open(replica_path, 'r', encoding='utf-8') as f:
            sentences = json.load(f)
        debug_log(f"Loaded {len(sentences)} sentences from Replica.json", "GOOD")
        return sentences
    except Exception as e:
        debug_log(f"Failed to load Replica.json: {e}, using fallback", "WARN")
        return ["Test note for verification."]


REPLICA_SENTENCES = load_replica_sentences()


def get_random_sentence() -> str:
    """Возвращает случайное предложение"""
    sentence = random.choice(REPLICA_SENTENCES)
    debug_log(f"Selected sentence: '{sentence}'", "INFO")
    return sentence


def generate_random_string(prefix: str, length: int = 32) -> str:
    """Генерирует строку вида {prefix}_{случайные символы}"""
    random_part = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))
    return f"{prefix}_{random_part}"


def generate_login() -> str:
    login = generate_random_string("user")
    debug_log(f"Generated login: {login}", "INFO")
    return login


def generate_password() -> str:
    password = generate_random_string("pass")
    debug_log(f"Generated password: {password}", "INFO")
    return password


# ==================== TRANSFORMATION HANDLERS ====================
def reverse_transform_transformed(transformed_data: str) -> str:
    """
    Восстанавливает оригинальный текст из трансформированного.
    Алгоритм обратный к transform_note_content в сервере:
    1. Переворот строки
    2. Реверс блоков по 4 символа
    3. Удаление префикса/суффикса (10000 символов с каждой стороны)
    """
    if not transformed_data:
        return ""

    # Шаг 1: Переворот строки
    content = list(transformed_data)
    content.reverse()
    debug_log(f"After reverse: first 50 chars: {''.join(content[:50])}...", "INFO")

    # Шаг 2: Реверс блоков по 4 символа
    total_len = len(content)
    new_content = content[:]
    for i in range(0, total_len - 3, 4):
        new_content[i:i + 4] = reversed(content[i:i + 4])
    content = new_content
    debug_log(f"After block reverse: first 50 chars: {''.join(content[:50])}...", "INFO")

    # Шаг 3: Удаление префикса/суффикса
    if len(content) > 20000:
        result = ''.join(content[10000:10000 + len(content) - 20000])
        debug_log(f"Extracted content (len: {len(result)}): '{result[:50]}...'", "INFO")
        return result

    result = ''.join(content)
    debug_log(f"Extracted content (len: {len(result)}): '{result[:50]}...'", "INFO")
    return result


def find_original_in_transformed(original: str, transformed: str) -> bool:
    """Проверяет, содержится ли оригинальный текст в трансформированном"""
    debug_log(f"Looking for original in transformed content", "INFO")
    debug_log(f"Original: '{original}'", "INFO")
    debug_log(f"Transformed (first 100 chars): '{transformed[:100]}...'", "INFO")
    
    restored = reverse_transform_transformed(transformed)
    found = original == restored or original in restored
    
    if found:
        debug_log(f"Found original in transformed content!", "GOOD")
    else:
        debug_log(f"Original NOT found in transformed content", "ERROR")
        debug_log(f"Restored: '{restored[:100]}...'", "ERROR")
    
    return found


# ==================== TOKEN VALIDATION ====================
def verify_token_format(full_token: str, expected_user_id: str) -> Tuple[bool, Optional[str]]:
    """
    Проверяет формат токена: {token_part}_{ids_count}_{user_id}
    """
    debug_log(f"Verifying token: '{full_token}'", "INFO")
    
    if not full_token:
        return False, "No token provided"

    parts = full_token.split('_')
    if len(parts) != 3:
        return False, f"Invalid token format (need 3 parts): {full_token}"

    token_part, ids_count_str, user_id_part = parts
    debug_log(f"Token parts: token={token_part}, count={ids_count_str}, user={user_id_part}", "INFO")

    # Проверка токена (16 hex символов)
    if not re.match(r'^[a-f0-9]{16}$', token_part):
        return False, f"Invalid token part: {token_part}"

    # Проверка ids_count
    if not ids_count_str.isdigit():
        return False, f"ids_count not a number: {ids_count_str}"

    ids_count = int(ids_count_str)
    if ids_count > HISTORY_SIZE:
        return False, f"ids_count {ids_count} exceeds {HISTORY_SIZE}"

    # Проверка user_id
    if user_id_part != expected_user_id:
        return False, f"User_id mismatch: {user_id_part} != {expected_user_id}"

    # Токен не должен быть нулевым
    if token_part == "0000000000000000":
        return False, "Token is zero value"

    debug_log(f"Token format is valid!", "GOOD")
    return True, None


# ==================== SOCKET CLIENT ====================
class SecureNoteClient:
    """Клиент для взаимодействия с Secure Note Server"""

    def __init__(self, host: str, port: int = PORT):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.buffer = ""
        self.authenticated = False
        self.current_user_id: Optional[str] = None

    def connect(self) -> None:
        """Установка соединения"""
        debug_log(f"Connecting to {self.host}:{self.port}", "INFO")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(SOCKET_TIMEOUT)
        self.sock.connect((self.host, self.port))
        self._read_until("Выберите действие:")
        debug_log("Connection established", "GOOD")

    def close(self) -> None:
        """Закрытие соединения"""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _recv_data(self, size: int = 8192) -> str:
        """Получение данных из сокета"""
        chunk = self.sock.recv(size).decode('utf-8', errors='replace')
        if not chunk:
            raise ConnectionError("Connection closed")
        return chunk

    def _read_until(self, expected: str, timeout: float = SOCKET_TIMEOUT) -> str:
        """Чтение данных до ожидаемой строки"""
        self.sock.settimeout(timeout)
        try:
            while expected not in self.buffer:
                self.buffer += self._recv_data()
            pos = self.buffer.find(expected) + len(expected)
            result = self.buffer[:pos]
            self.buffer = self.buffer[pos:]
            if DEBUG:
                debug_log(f"Read until '{expected}': {len(result)} chars", "INFO")
            return result
        except socket.timeout:
            raise TimeoutError(f"Timeout waiting for '{expected}'")
        finally:
            self.sock.settimeout(SOCKET_TIMEOUT)

    def _read_line(self, timeout: float = SOCKET_TIMEOUT) -> str:
        """Чтение одной строки"""
        self.sock.settimeout(timeout)
        try:
            while '\n' not in self.buffer:
                self.buffer += self._recv_data()
            pos = self.buffer.find('\n') + 1
            line = self.buffer[:pos].rstrip('\n\r')
            self.buffer = self.buffer[pos:]
            if DEBUG:
                debug_log(f"Read line: '{line}'", "INFO")
            return line
        except socket.timeout:
            raise TimeoutError("Timeout reading line")
        finally:
            self.sock.settimeout(SOCKET_TIMEOUT)

    def send_line(self, line: str) -> None:
        """Отправка строки"""
        try:
            self.sock.send((line + "\n").encode('utf-8'))
            if DEBUG and len(line) < 100:
                debug_log(f"Sent: '{line}'", "INFO")
            elif DEBUG:
                debug_log(f"Sent: '{line[:50]}...' (len={len(line)})", "INFO")
        except socket.error as e:
            raise ConnectionError(f"Failed to send data: {e}")

    # ========== API METHODS ==========
    def register(self, login: str, password: str) -> Optional[str]:
        """Регистрация нового пользователя"""
        debug_log(f"=== REGISTER: {login} ===", "INFO")

        self.send_line("1")
        self._read_until("=== Регистрация ===")
        self._read_until("Логин:")
        self.send_line(login)
        self._read_until("Пароль:")
        self.send_line(password)

        response = self._read_line()
        debug_log(f"Register response: '{response}'", "INFO")

        if "Ваш user_id:" in response:
            user_id = response.split("Ваш user_id:")[-1].strip()
            if user_id and re.match(r'^[a-f0-9]{32}$', user_id):
                debug_log(f"Registration successful, user_id: {user_id}", "GOOD")
                return user_id

        debug_log("Registration failed", "ERROR")
        return None

    def login(self, login: str, password: str) -> bool:
        """Авторизация"""
        debug_log(f"=== LOGIN: {login} ===", "INFO")

        self.send_line("2")
        self._read_until("=== Авторизация ===")
        self._read_until("Логин:")
        self.send_line(login)
        self._read_until("Пароль:")
        self.send_line(password)

        response = self._read_until("--- Меню ---")
        success = "Добро пожаловать" in response

        if success:
            debug_log(f"Login successful for {login}", "GOOD")
            self.authenticated = True
            match = re.search(r'user_id: ([a-f0-9]{32})', response)
            if match:
                self.current_user_id = match.group(1)
                debug_log(f"Current user_id: {self.current_user_id}", "INFO")
        else:
            debug_log(f"Login failed for {login}", "ERROR")

        return success

    def write_note(self, note: str) -> bool:
        """Запись заметки"""
        debug_log(f"=== WRITE NOTE (len={len(note)}) ===", "INFO")
        debug_log(f"Note content: '{note}'", "INFO")

        self.send_line("1")
        self._read_until("=== Запись заметки ===")
        self._read_until("текст (можно пустую строку):")
        self.send_line(note)

        response = self._read_until("--- Меню ---")
        success = "Заметка сохранена" in response
        
        if success:
            debug_log("Note written successfully", "GOOD")
        else:
            debug_log("Note write failed", "ERROR")
        
        return success

    def read_note(self, user_id: str) -> str:
        """Чтение заметки"""
        debug_log(f"=== READ NOTE: {user_id} ===", "INFO")

        self.send_line("2")
        self._read_until("=== Чтение заметки ===")
        self._read_until("Введите ваш user_id")
        self.send_line(user_id)

        result = ""
        while True:
            line = self._read_line()
            result += line + "\n"
            if "--- Меню ---" in line:
                break

        if DEBUG:
            # Показываем извлеченную заметку
            note = self.extract_note(result)
            if note:
                debug_log(f"Extracted note: '{note}'", "INFO")
            token = self.extract_token(result)
            if token:
                debug_log(f"Extracted token: '{token}'", "INFO")

        return result

    def download_note(self, target_id: str) -> str:
        """Скачивание заметки (с трансформацией)"""
        debug_log(f"=== DOWNLOAD NOTE: {target_id} ===", "INFO")

        self.send_line("3")
        self._read_until("=== Скачать заметку ===")
        self._read_until("Введите user_id для скачивания:")
        self.send_line(target_id)

        try:
            response = self._read_until("=== КОНЕЦ ЗАМЕТКИ ===")
            if DEBUG:
                # Показываем размер полученных данных
                debug_log(f"Downloaded {len(response)} chars of transformed content", "INFO")
                # Показываем начало и конец трансформированного содержимого
                if "=== ПОЛНОЕ СОДЕРЖИМОЕ ЗАМЕТКИ ===" in response:
                    parts = response.split("=== ПОЛНОЕ СОДЕРЖИМОЕ ЗАМЕТКИ ===")
                    if len(parts) > 1:
                        content = parts[1].split("=== КОНЕЦ ЗАМЕТКИ ===")[0].strip()
                        debug_log(f"Transformed content (first 100 chars): '{content[:100]}...'", "INFO")
                        debug_log(f"Transformed content (last 100 chars): '...{content[-100:]}'", "INFO")
            return response
        except (TimeoutError, ConnectionError) as e:
            debug_log(f"Download failed: {e}", "ERROR")
            return ""

    def logout(self) -> None:
        """Выход из аккаунта"""
        debug_log("=== LOGOUT ===", "INFO")
        self.send_line("4")
        self._read_until("=== Secure Note ===")
        self.authenticated = False
        self.current_user_id = None
        debug_log("Logged out successfully", "GOOD")

    # ========== EXTRACTORS ==========
    def extract_note(self, response: str) -> Optional[str]:
        """Извлечение заметки из ответа"""
        for line in response.split('\n'):
            if "Ваша заметка:" in line:
                note = line.split("Ваша заметка:")[-1].strip()
                return note
        return None

    def extract_token(self, response: str) -> Optional[str]:
        """Извлечение токена из ответа"""
        for line in response.split('\n'):
            if "Токен текущей операции:" in line:
                token = line.split("Токен текущей операции:")[-1].strip()
                return token
        return None


# ==================== VERIFICATION FUNCTIONS ====================
def verify_read_note_with_token(client: SecureNoteClient, user_id: str,
                                expected_content: str) -> Tuple[bool, Optional[str]]:
    """
    Проверяет чтение заметки вместе с токеном операции
    """
    debug_log("=== VERIFY READ NOTE WITH TOKEN ===", "INFO")
    
    # Первое чтение
    response1 = client.read_note(user_id)

    # Проверяем содержимое заметки
    note = client.extract_note(response1)
    if note != expected_content:
        return False, f"Note mismatch. Expected: '{expected_content}', Got: '{note}'"
    debug_log("Note content verified", "GOOD")

    # Проверяем токен
    token1 = client.extract_token(response1)
    if not token1:
        return False, "No operation token found"
    debug_log(f"First token: {token1}", "INFO")

    valid, err = verify_token_format(token1, user_id)
    if not valid:
        return False, err

    # Второе чтение для проверки сохранения токена
    debug_log("Reading note second time to verify token persistence", "INFO")
    response2 = client.read_note(user_id)
    token2 = client.extract_token(response2)

    if not token2:
        return False, "No token in second read"
    debug_log(f"Second token: {token2}", "INFO")

    valid, err = verify_token_format(token2, user_id)
    if not valid:
        return False, f"Second token invalid: {err}"

    # ids_count не должен уменьшаться
    count1 = int(token1.split('_')[1])
    count2 = int(token2.split('_')[1])
    if count2 < count1:
        return False, f"ids_count decreased: {count2} < {count1}"
    
    if count2 == count1:
        debug_log(f"ids_count preserved: {count1}", "GOOD")
    else:
        debug_log(f"ids_count increased: {count1} -> {count2}", "INFO")

    debug_log("Token verification passed", "GOOD")
    return True, None


def verify_download_note(client: SecureNoteClient, target_id: str,
                          expected_content: str) -> Tuple[bool, Optional[str]]:
    """
    Проверяет, что скачанная заметка содержит ожидаемый контент
    """
    debug_log("=== VERIFY DOWNLOAD NOTE ===", "INFO")
    
    response = client.download_note(target_id)

    if not response:
        return False, "Download failed - no response"

    # Проверяем через обратную трансформацию
    if "=== ПОЛНОЕ СОДЕРЖИМОЕ ЗАМЕТКИ ===" in response:
        debug_log("Found transformed content marker", "INFO")
        parts = response.split("=== ПОЛНОЕ СОДЕРЖИМОЕ ЗАМЕТКИ ===")
        if len(parts) > 1:
            content_part = parts[1].split("=== КОНЕЦ ЗАМЕТКИ ===")[0].strip()
            if find_original_in_transformed(expected_content, content_part):
                debug_log("Content verified via reverse transformation", "GOOD")
                return True, None

    # Fallback: проверка через read_note
    debug_log("Trying fallback verification via read_note", "INFO")
    read_response = client.read_note(target_id)
    if expected_content in read_response:
        debug_log("Content verified via read_note", "GOOD")
        return True, None

    debug_log("Content verification failed", "ERROR")
    return False, "Expected content not found"


# ==================== EXIT HANDLING ====================
class ExitStatus(Enum):
    OK = 101
    CORRUPT = 102
    MUMBLE = 103
    DOWN = 104
    CHECKER_ERROR = 110


def die(code: ExitStatus, msg: str = "") -> None:
    """Завершение работы с указанным статусом"""
    if msg:
        print(msg, file=sys.stderr, flush=True)
    debug_log(f"Exiting with status: {code.name} ({code.value})", "INFO")
    sys.exit(code.value)


def print_ok() -> None:
    print("OK", flush=True)


# ==================== CHECKER ACTIONS ====================
def check(host: str) -> None:
    """Проверка работоспособности сервиса"""
    debug_log("=" * 60, "INFO")
    debug_log("STARTING CHECK ACTION", "INFO")
    debug_log("=" * 60, "INFO")

    try:
        with SecureNoteClient(host, PORT) as client:
            # Шаг 1: Регистрация
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 1: REGISTRATION", "INFO")
            debug_log("=" * 40, "INFO")
            
            login = generate_login()
            password = generate_password()
            user_id = client.register(login, password)
            if not user_id:
                die(ExitStatus.MUMBLE, "Registration failed")
            debug_log(f"User ID: {user_id}", "GOOD")
            
            # Шаг 2: Авторизация
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 2: LOGIN", "INFO")
            debug_log("=" * 40, "INFO")
            
            if not client.login(login, password):
                die(ExitStatus.MUMBLE, "Login failed")
            
            # Шаг 3: Запись заметки
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 3: WRITE NOTE", "INFO")
            debug_log("=" * 40, "INFO")
            
            note = get_random_sentence()
            if not client.write_note(note):
                die(ExitStatus.MUMBLE, "Write note failed")
            
            # Шаг 4: Чтение с проверкой токена
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 4: READ NOTE WITH TOKEN", "INFO")
            debug_log("=" * 40, "INFO")
            
            success, err = verify_read_note_with_token(client, user_id, note)
            if not success:
                die(ExitStatus.CORRUPT, err)
            
            # Шаг 5: Скачивание с проверкой содержимого
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 5: DOWNLOAD NOTE", "INFO")
            debug_log("=" * 40, "INFO")
            
            success, err = verify_download_note(client, user_id, note)
            if not success:
                die(ExitStatus.MUMBLE, err)
            
            # Шаг 6: Выход
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 6: LOGOUT", "INFO")
            debug_log("=" * 40, "INFO")
            
            client.logout()

        debug_log("\n" + "=" * 60, "INFO")
        debug_log("CHECK ACTION COMPLETED SUCCESSFULLY", "GOOD")
        debug_log("=" * 60, "INFO")

        print_ok()
        die(ExitStatus.OK)

    except (ConnectionError, TimeoutError, socket.error) as e:
        debug_log(f"Connection error: {e}", "ERROR")
        die(ExitStatus.DOWN, str(e))
    except Exception as e:
        debug_log(f"Unexpected error: {e}", "ERROR")
        import traceback
        debug_log(traceback.format_exc(), "ERROR")
        die(ExitStatus.CHECKER_ERROR, str(e))


def put(host: str, flag_id: str, flag: str, vuln: int) -> None:
    """Сохранение флага"""
    debug_log("=" * 60, "INFO")
    debug_log("STARTING PUT ACTION", "INFO")
    debug_log("=" * 60, "INFO")
    debug_log(f"Flag: {flag}", "INFO")

    login = generate_login()
    password = generate_password()

    try:
        with SecureNoteClient(host, PORT) as client:
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 1: REGISTRATION", "INFO")
            debug_log("=" * 40, "INFO")
            
            user_id = client.register(login, password)
            if not user_id:
                die(ExitStatus.MUMBLE, "Registration failed")
            debug_log(f"User ID: {user_id}", "GOOD")
            
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 2: LOGIN", "INFO")
            debug_log("=" * 40, "INFO")
            
            if not client.login(login, password):
                die(ExitStatus.MUMBLE, "Login failed")
            
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 3: WRITE FLAG", "INFO")
            debug_log("=" * 40, "INFO")
            
            if not client.write_note(flag):
                die(ExitStatus.MUMBLE, "Write note failed")

        flag_id_data = json.dumps({"login": login, "password": password, "user_id": user_id})

        debug_log("\n" + "=" * 60, "INFO")
        debug_log("PUT ACTION COMPLETED SUCCESSFULLY", "GOOD")
        debug_log("=" * 60, "INFO")
        debug_log(f"Flag ID: {flag_id_data}", "INFO")

        print_ok()
        sys.stderr.write(flag_id_data + "\n")
        sys.stderr.flush()
        die(ExitStatus.OK)

    except (ConnectionError, TimeoutError, socket.error) as e:
        debug_log(f"Connection error: {e}", "ERROR")
        die(ExitStatus.DOWN, str(e))
    except Exception as e:
        debug_log(f"Unexpected error: {e}", "ERROR")
        import traceback
        debug_log(traceback.format_exc(), "ERROR")
        die(ExitStatus.CHECKER_ERROR, str(e))


def get(host: str, flag_id: str, flag: str, vuln: int) -> None:
    """Получение флага"""
    debug_log("=" * 60, "INFO")
    debug_log("STARTING GET ACTION", "INFO")
    debug_log("=" * 60, "INFO")
    debug_log(f"Looking for flag: {flag}", "INFO")

    try:
        data = json.loads(flag_id)
        login = data.get("login")
        password = data.get("password")
        user_id = data.get("user_id")
        debug_log(f"Restoring account: {login}, user_id: {user_id}", "INFO")
    except Exception as e:
        debug_log(f"Invalid flag_id: {e}", "ERROR")
        die(ExitStatus.CORRUPT, f"Invalid flag_id: {e}")

    try:
        with SecureNoteClient(host, PORT) as client:
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 1: LOGIN", "INFO")
            debug_log("=" * 40, "INFO")
            
            if not client.login(login, password):
                die(ExitStatus.CORRUPT, "Login failed")
            
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 2: READ NOTE", "INFO")
            debug_log("=" * 40, "INFO")
            
            response = client.read_note(user_id)
            if flag not in response:
                debug_log(f"Flag not found in response", "ERROR")
                die(ExitStatus.CORRUPT, "Flag not found in read_note")
            debug_log(f"Flag found in read_note!", "GOOD")
            
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 3: VERIFY TOKEN", "INFO")
            debug_log("=" * 40, "INFO")
            
            token = client.extract_token(response)
            if not token:
                die(ExitStatus.CORRUPT, "No operation token found")
            
            valid, err = verify_token_format(token, user_id)
            if not valid:
                die(ExitStatus.CORRUPT, err)
            
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 4: VERIFY TOKEN PERSISTENCE", "INFO")
            debug_log("=" * 40, "INFO")
            
            response2 = client.read_note(user_id)
            token2 = client.extract_token(response2)
            if not token2:
                die(ExitStatus.CORRUPT, "No token in second read")
            
            valid, err = verify_token_format(token2, user_id)
            if not valid:
                die(ExitStatus.CORRUPT, err)
            
            debug_log("\n" + "=" * 40, "INFO")
            debug_log("STEP 5: VERIFY VIA DOWNLOAD", "INFO")
            debug_log("=" * 40, "INFO")
            
            success, err = verify_download_note(client, user_id, flag)
            if not success:
                die(ExitStatus.CORRUPT, err)

        debug_log("\n" + "=" * 60, "INFO")
        debug_log("GET ACTION COMPLETED SUCCESSFULLY", "GOOD")
        debug_log("=" * 60, "INFO")
        die(ExitStatus.OK, "OK")

    except (ConnectionError, TimeoutError, socket.error) as e:
        debug_log(f"Connection error: {e}", "ERROR")
        die(ExitStatus.DOWN, str(e))
    except Exception as e:
        debug_log(f"Unexpected error: {e}", "ERROR")
        import traceback
        debug_log(traceback.format_exc(), "ERROR")
        die(ExitStatus.CHECKER_ERROR, str(e))


def info() -> None:
    """Информация об уязвимостях"""
    print("vulns: 1:1", flush=True)
    die(ExitStatus.OK)


# ==================== MAIN ====================
def _main() -> None:
    # Импортируем argv из sys
    from sys import argv
    
    try:
        cmd = argv[1]

        # Обработка флага --debug
        if len(argv) > 2 and argv[2] == '--debug':
            global DEBUG
            DEBUG = True
            debug_log("Debug mode enabled", "GOOD")
            host = argv[3] if len(argv) > 3 else None
        else:
            host = argv[2] if len(argv) > 2 else None

        if cmd == "info":
            info()
        elif cmd == "check":
            check(host)
        elif cmd == "put":
            put(argv[2], argv[3], argv[4], int(argv[5]))
        elif cmd == "get":
            get(argv[2], argv[3], argv[4], int(argv[5]))
        else:
            raise IndexError
    except IndexError:
        die(ExitStatus.CHECKER_ERROR, "Invalid arguments")
    except Exception as e:
        die(ExitStatus.CHECKER_ERROR, str(e))


if __name__ == "__main__":
    _main()
