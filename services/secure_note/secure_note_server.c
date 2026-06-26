#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <time.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <stdarg.h>

#define PORT 4444
#define MAX_LOGIN_LEN 50
#define MAX_PASS_LEN 50
#define HASH_LEN 32
#define USER_ID_LEN 32
#define NOTE_MAX_LEN 256
#define MAX_LINE_LEN 512
#define HISTORY_SIZE 10

typedef struct {
    char login[MAX_LOGIN_LEN];
    char password_hash[HASH_LEN + 1];
    char user_id[USER_ID_LEN + 1];
} User;

char current_user_id[USER_ID_LEN + 1] = {0};
char current_login[MAX_LOGIN_LEN] = {0};

// Глобальный сокет для отправки ответов
int client_socket = -1;

// Функции для работы через сокет
void send_str(const char *str) {
    if (client_socket >= 0)
        send(client_socket, str, strlen(str), 0);
    else
        printf("%s", str);
}

// Буфер для передачи содержимого клиенту
void send_printf(const char *format, ...) {
    char buffer[65536];
    va_list args;
    va_start(args, format);
    vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    send_str(buffer);
}

void get_input(char *buffer, int size) {
    int i = 0;
    char c;
    while (i < size - 1) {
        if (recv(client_socket, &c, 1, 0) <= 0) {
            buffer[i] = '\0';
            return;
        }
        if (c == '\n') {
            buffer[i] = '\0';
            return;
        }
        if (c == '\r') continue;
        buffer[i++] = c;
    }
    buffer[i] = '\0';
}

void simple_hash(const char *input, char *output) {
    unsigned long hash = 5381;
    int c;
    while ((c = *input++)) {
        hash = ((hash << 5) + hash) + c;
    }
    sprintf(output, "%016lx", hash);
}

void generate_user_id(char *user_id) {
    const char hex_chars[] = "0123456789abcdef";
    for (int i = 0; i < USER_ID_LEN; i++) {
        user_id[i] = hex_chars[rand() % 16];
    }
    user_id[USER_ID_LEN] = '\0';
}

int is_user_id_unique(const char *user_id) {
    FILE *file = fopen("data/users.txt", "r");
    if (!file) return 1;
    char line[MAX_LINE_LEN];
    char login[MAX_LOGIN_LEN], hash[HASH_LEN + 1], existing_id[USER_ID_LEN + 1];
    while (fgets(line, sizeof(line), file)) {
        line[strcspn(line, "\n")] = 0;
        if (sscanf(line, "%[^,],%[^,],%s", login, hash, existing_id) == 3) {
            if (strcmp(existing_id, user_id) == 0) {
                fclose(file);
                return 0;
            }
        }
    }
    fclose(file);
    return 1;
}

void create_unique_user_id(char *user_id) {
    do {
        generate_user_id(user_id);
    } while (!is_user_id_unique(user_id));
}

void create_directories() {
    mkdir("data", 0755);
    mkdir("data/notes", 0755);
}

// ========== ФУНКЦИИ ДЛЯ РАБОТЫ С LAST_IDS ==========
typedef struct {
    char ids[HISTORY_SIZE][USER_ID_LEN + 1];
    int count;
} LastIdsData;

// Функция для сохранения last_ids
void save_last_ids(const char *user_id, char last_ids[HISTORY_SIZE][USER_ID_LEN + 1], int ids_count) {
    char path[256];
    snprintf(path, sizeof(path), "data/notes/%s.last_ids", user_id);
    
    FILE *f = fopen(path, "w");
    if (!f) return;
    
    fprintf(f, "%d\n", ids_count);
    for (int i = 0; i < ids_count && i < HISTORY_SIZE; i++) {
        fprintf(f, "%s\n", last_ids[i]);
    }
    fclose(f);
}

// Функция для чтения last_ids
int read_last_ids(const char *user_id, char last_ids[HISTORY_SIZE][USER_ID_LEN + 1], int *ids_count) {
    char path[256];
    snprintf(path, sizeof(path), "data/notes/%s.last_ids", user_id);
    
    FILE *f = fopen(path, "r");
    if (!f) return 0;
    
    if (fscanf(f, "%d\n", ids_count) != 1) {
        fclose(f);
        return 0;
    }
    
    for (int i = 0; i < *ids_count && i < HISTORY_SIZE; i++) {
        if (fgets(last_ids[i], USER_ID_LEN + 1, f)) {
            last_ids[i][strcspn(last_ids[i], "\n")] = 0;
        }
    }
    fclose(f);
    return 1;
}

// ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ТОКЕНАМИ ==========
// Функция для сохранения токена в отдельный файл
void save_token(const char *user_id, const char *token) {
    char token_path[256];
    snprintf(token_path, sizeof(token_path), "data/notes/%s.token", user_id);
    
    FILE *token_file = fopen(token_path, "w");
    if (token_file) {
        fprintf(token_file, "%s", token);
        fclose(token_file);
    }
}

// Функция для чтения сохраненного токена
int read_saved_token(const char *user_id, char *token) {
    char token_path[256];
    snprintf(token_path, sizeof(token_path), "data/notes/%s.token", user_id);
    
    FILE *token_file = fopen(token_path, "r");
    if (token_file) {
        if (fgets(token, 33, token_file)) {
            token[strcspn(token, "\n")] = 0;
            fclose(token_file);
            return 1; // Токен успешно прочитан
        }
        fclose(token_file);
    }
    return 0; // Токен не найден
}

// Функция для удаления сохраненного токена
void delete_token(const char *user_id) {
    char token_path[256];
    snprintf(token_path, sizeof(token_path), "data/notes/%s.token", user_id);
    remove(token_path);
}

// Функция для удаления сохраненных last_ids
void delete_last_ids(const char *user_id) {
    char path[256];
    snprintf(path, sizeof(path), "data/notes/%s.last_ids", user_id);
    remove(path);
}

// Функция для генерации токена на основе last_ids и current_user_id
void generate_token_from_ids(char *token, char last_ids[HISTORY_SIZE][USER_ID_LEN + 1], int ids_count) {
    const char charset[] = "0123456789abcdef";
    
    // Формируем строку из last_ids и current_user_id
    char combined[1024] = {0};
    for (int i = 0; i < ids_count && i < HISTORY_SIZE; i++) {
        strcat(combined, last_ids[i]);
        if (i < ids_count - 1) strcat(combined, ":"); // разделитель
    }
    
    // Добавляем current_user_id для уникальности
    strcat(combined, "|");
    strcat(combined, current_user_id);
    
    // Генерируем хеш от combined
    char hash_buf[33] = {0};
    simple_hash(combined, hash_buf);
    
    // Берем первые 32 символа хеша и приводим к нижнему регистру
    for (int i = 0; i < 32 && hash_buf[i] != '\0'; i++) {
        token[i] = tolower(hash_buf[i]);
    }
    token[32] = '\0';
    
    // Если по какой-то причине токен пустой, используем fallback
    if (strlen(token) == 0) {
        for (int i = 0; i < 32; i++) {
            token[i] = charset[rand() % 16];
        }
        token[32] = '\0';
    }
}

int register_user() {
    char login[MAX_LOGIN_LEN];
    char password[MAX_PASS_LEN];
    char password_hash[HASH_LEN + 1];
    char user_id[USER_ID_LEN + 1];
    
    send_printf("\n=== Регистрация ===\n");
    send_printf("Логин: ");
    get_input(login, sizeof(login));
    
    if (strlen(login) == 0) {
        send_printf("Ошибка: логин не может быть пустым!\n");
        return 0;
    }
    
    FILE *users_file = fopen("data/users.txt", "r");
    if (users_file) {
        char line[MAX_LINE_LEN], existing_login[MAX_LOGIN_LEN];
        while (fgets(line, sizeof(line), users_file)) {
            line[strcspn(line, "\n")] = 0;
            sscanf(line, "%[^,],%*[^,],%*s", existing_login);
            if (strcmp(existing_login, login) == 0) {
                send_printf("Ошибка: пользователь с таким логином уже существует!\n");
                fclose(users_file);
                return 0;
            }
        }
        fclose(users_file);
    }
    
    send_printf("Пароль: ");
    get_input(password, sizeof(password));
    
    if (strlen(password) == 0) {
        send_printf("Ошибка: пароль не может быть пустым!\n");
        return 0;
    }
    
    simple_hash(password, password_hash);
    create_unique_user_id(user_id);
    
    users_file = fopen("data/users.txt", "a");
    if (!users_file) {
        send_printf("Ошибка: не удалось открыть файл пользователей!\n");
        return 0;
    }
    fprintf(users_file, "%s,%s,%s\n", login, password_hash, user_id);
    fclose(users_file);
    
    char note_path[256];
    snprintf(note_path, sizeof(note_path), "data/notes/%s.txt", user_id);
    FILE *note_file = fopen(note_path, "w");
    if (note_file) fclose(note_file);
    
    send_printf("Регистрация успешна! Ваш user_id: %s\n", user_id);
    return 1;
}

int login() {
    char login[MAX_LOGIN_LEN];
    char password[MAX_PASS_LEN];
    char password_hash[HASH_LEN + 1];
    
    send_printf("\n=== Авторизация ===\n");
    send_printf("Логин: ");
    get_input(login, sizeof(login));
    
    send_printf("Пароль: ");
    get_input(password, sizeof(password));
    
    simple_hash(password, password_hash);
    
    FILE *users_file = fopen("data/users.txt", "r");
    if (!users_file) {
        send_printf("Ошибка: файл пользователей не найден!\n");
        return 0;
    }
    
    char line[MAX_LINE_LEN];
    char stored_login[MAX_LOGIN_LEN];
    char stored_hash[HASH_LEN + 1];
    char stored_id[USER_ID_LEN + 1];
    
    while (fgets(line, sizeof(line), users_file)) {
        line[strcspn(line, "\n")] = 0;
        if (sscanf(line, "%[^,],%[^,],%s", stored_login, stored_hash, stored_id) == 3) {
            if (strcmp(stored_login, login) == 0 && strcmp(stored_hash, password_hash) == 0) {
                strcpy(current_user_id, stored_id);
                strcpy(current_login, stored_login);
                fclose(users_file);
                send_printf("\nДобро пожаловать, %s! Ваш user_id: %s\n", current_login, current_user_id);
                return 1;
            }
        }
    }
    
    fclose(users_file);
    send_printf("Ошибка: неверный логин или пароль!\n");
    return 0;
}

void write_note() {
    char note[NOTE_MAX_LEN + 2];
    
    while (1) {
        send_printf("\n=== Запись заметки ===\n");
        send_printf("Максимум %d символов. Введите текст (можно пустую строку):\n", NOTE_MAX_LEN);
        
        get_input(note, sizeof(note));
        
        int too_long = 0;
        if (strlen(note) == NOTE_MAX_LEN + 1 && note[NOTE_MAX_LEN] != '\n') {
            too_long = 1;
            char c;
            while (recv(client_socket, &c, 1, 0) > 0 && c != '\n');
        }
        
        if (too_long || strlen(note) > NOTE_MAX_LEN) {
            send_printf("Ошибка: вы ввели слишком много символов\n");
            continue;
        }
        
        char note_path[256];
        snprintf(note_path, sizeof(note_path), "data/notes/%s.txt", current_user_id);
        FILE *note_file = fopen(note_path, "w");
        if (!note_file) {
            send_printf("Ошибка: не удалось сохранить заметку!\n");
            return;
        }
        
        fprintf(note_file, "%s", note);
        fclose(note_file);
        
        // Удаляем старый токен и last_ids, так как заметка изменилась
        delete_token(current_user_id);
        delete_last_ids(current_user_id);
        
        send_printf("Заметка сохранена!\n");
        break;
    }
}

void read_note() {
    char input_id[USER_ID_LEN + 10];
    char last_ids[HISTORY_SIZE][USER_ID_LEN + 1];
    int ids_count = 0;
    
    char line[MAX_LINE_LEN];
    char login[MAX_LOGIN_LEN];
    char hash[HASH_LEN + 1];
    char id[USER_ID_LEN + 1];
    char temp_ids[1000][USER_ID_LEN + 1];
    int total = 0;
    
    // Заполняем last_ids последними HISTORY_SIZE пользователями
    FILE *f = fopen("data/users.txt", "r");
    if (f) {
        while (fgets(line, sizeof(line), f)) {
            line[strcspn(line, "\n")] = 0;
            if (sscanf(line, "%[^,],%[^,],%s", login, hash, id) == 3) {
                strcpy(temp_ids[total++], id);
                if (total >= 1000) break;
            }
        }
        fclose(f);
        
        int start = total > HISTORY_SIZE ? total - HISTORY_SIZE : 0;
        ids_count = total - start;
        
        for (int i = 0; i < ids_count; i++) {
            strcpy(last_ids[i], temp_ids[start + i]);
        }
        for (int i = ids_count; i < HISTORY_SIZE; i++) {
            last_ids[i][0] = '\0';
        }
    }
    
    // СОХРАНЯЕМ last_ids ДЛЯ ПОЛЬЗОВАТЕЛЯ
    save_last_ids(current_user_id, last_ids, ids_count);
    
    send_printf("\n=== Чтение заметки ===\n");
    send_printf("Введите ваш user_id (или 'q' для выхода): ");
    get_input(input_id, sizeof(input_id));
    
    if (strcmp(input_id, "q") == 0) return;
    
    if (strcmp(input_id, current_user_id) != 0) {
        send_printf("Ошибка: доступ запрещён\n");
        return;
    }
    
    // Проверяем, существует ли файл заметки
    char note_path[256];
    snprintf(note_path, sizeof(note_path), "data/notes/%s.txt", current_user_id);
    
    FILE *note_file = fopen(note_path, "r");
    if (!note_file) {
        send_printf("Ваша заметка пуста\n");
        return;
    }
    
    // ===== ГЕНЕРАЦИЯ/ЧТЕНИЕ ТОКЕНА =====
    char operation_token[33] = {0};
    
    // Пытаемся прочитать сохраненный токен
    if (!read_saved_token(current_user_id, operation_token)) {
        // Если токена нет - генерируем и сохраняем
        generate_token_from_ids(operation_token, last_ids, ids_count);
        save_token(current_user_id, operation_token);
    } 
    // ===== КОНЕЦ ГЕНЕРАЦИИ/ЧТЕНИЯ ТОКЕНА =====
    
    char note[NOTE_MAX_LEN + 100];
    if (fgets(note, sizeof(note), note_file)) {
        note[strcspn(note, "\n")] = 0;
        char full_token[128] = {0};
        snprintf(full_token, sizeof(full_token), "%s_%d_%s", operation_token, ids_count, current_user_id);
        send_printf("Токен текущей операции: %s\n", full_token);
        send_printf("Ваша заметка: ");
        send_printf(note);
        send_printf("\n");
    } else {
        send_printf("Ваша заметка пуста\n");
    }
    
    fclose(note_file);
}

void transform_note_content(char *content) {
    if (!content) return;
    size_t len = strlen(content);
    if (len == 0) return;
    
    int prefix_len = 10000;
    int suffix_len = 10000;
    char *new_content = malloc(prefix_len + len + suffix_len + 1);
    if (!new_content) return;
    
    const char *charset = 
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789"
        "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~ ";
    
    int charset_len = strlen(charset);
    
    for (int i = 0; i < prefix_len; i++) {
        new_content[i] = charset[rand() % charset_len];
    }
    memcpy(new_content + prefix_len, content, len);
    for (int i = 0; i < suffix_len; i++) {
        new_content[prefix_len + len + i] = charset[rand() % charset_len];
    }
    new_content[prefix_len + len + suffix_len] = '\0';
    
    size_t new_len = prefix_len + len + suffix_len;
    char *temp = malloc(new_len + 1);
    if (!temp) {
        free(new_content);
        return;
    }
    
    for (size_t i = 0; i < new_len; i += 4) {
        if (i + 3 < new_len) {
            temp[i] = new_content[i + 3];
            temp[i + 1] = new_content[i + 2];
            temp[i + 2] = new_content[i + 1];
            temp[i + 3] = new_content[i];
        } else {
            for (size_t j = i; j < new_len; j++) {
                temp[j] = new_content[j];
            }
        }
    }
    temp[new_len] = '\0';
    memcpy(new_content, temp, new_len + 1);
    free(temp);
    
    for (size_t i = 0; i < new_len / 2; i++) {
        char tmp = new_content[i];
        new_content[i] = new_content[new_len - 1 - i];
        new_content[new_len - 1 - i] = tmp;
    }
    
    strcpy(content, new_content);
    free(new_content);
}

void download_note() {
    char target_id[USER_ID_LEN + 10];
    
    send_printf("\n=== Скачать заметку ===\n");
    send_printf("Введите user_id для скачивания: ");
    get_input(target_id, sizeof(target_id));
    
    if (strlen(target_id) == 0) {
        send_printf("Ошибка: user_id не может быть пустым\n");
        return;
    }
    
    char note_path[256];
    snprintf(note_path, sizeof(note_path), "data/notes/%s.txt", target_id);
    
    FILE *note_file = fopen(note_path, "r");
    if (!note_file) {
        send_printf("Заметка для user_id %s не найдена или пуста\n", target_id);
        return;
    }
    
    // Читаем оригинальную заметку
    char original_note[NOTE_MAX_LEN + 2] = {0};
    if (!fgets(original_note, sizeof(original_note), note_file)) {
        send_printf("Заметка пуста\n");
        fclose(note_file);
        return;
    }
    original_note[strcspn(original_note, "\n")] = 0;
    fclose(note_file);
    
    if (strlen(original_note) == 0) {
        send_printf("Заметка пуста\n");
        return;
    }
    
    // Трансформируем содержимое
    char *transformed = malloc(strlen(original_note) + 20000 + 1);
    if (!transformed) {
        send_printf("Ошибка памяти\n");
        return;
    }
    strcpy(transformed, original_note);
    transform_note_content(transformed);
    
    // ВЫВОДИМ ПОЛНОСТЬЮ (без обрезания send_printf)
    send_printf("\n=== ПОЛНОЕ СОДЕРЖИМОЕ ЗАМЕТКИ ===\n");
    send_printf("%s\n", transformed);
    send_printf("=== КОНЕЦ ЗАМЕТКИ ===\n");
    
    free(transformed);
}

void logout() {
    current_user_id[0] = '\0';
    current_login[0] = '\0';
    send_printf("Выход из аккаунта.\n");
}

void handle_client(int client_fd) {
    client_socket = client_fd;
    int authenticated = 0;
    char choice_str[10];
    
    while (1) {
        if (!authenticated) {
            send_printf("\n=== Secure Note ===\n");
            send_printf("1. Регистрация\n");
            send_printf("2. Авторизация\n");
            send_printf("3. Выход\n");
            send_printf("Выберите действие: ");
            
            get_input(choice_str, sizeof(choice_str));
            int choice = atoi(choice_str);
            
            switch (choice) {
                case 1:
                    register_user();
                    break;
                case 2:
                    if (login()) authenticated = 1;
                    break;
                case 3:
                    send_printf("До свидания!\n");
                    close(client_socket);
                    return;
                default:
                    send_printf("Неверный выбор!\n");
            }
        } else {
            send_printf("\n--- Меню ---\n");
            send_printf("1. Запись заметки\n");
            send_printf("2. Чтение заметки\n");
            send_printf("3. Скачать заметку\n");
            send_printf("4. Выйти из аккаунта\n");
            send_printf("Выберите действие: ");
            
            get_input(choice_str, sizeof(choice_str));
            int choice = atoi(choice_str);
            
            switch (choice) {
                case 1:
                    write_note();
                    break;
                case 2:
                    read_note();
                    break;
                case 3:
                    download_note();
                    break;
                case 4:
                    logout();
                    authenticated = 0;
                    break;
                default:
                    send_printf("Неверный выбор!\n");
            }
        }
    }
}

int main() {
    srand(time(NULL));
    create_directories();
    
    int server_fd, client_fd;
    struct sockaddr_in server_addr, client_addr;
    socklen_t client_len = sizeof(client_addr);
    
    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        perror("Socket creation failed");
        exit(1);
    }
    
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(PORT);
    
    if (bind(server_fd, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        perror("Bind failed");
        exit(1);
    }
    
    if (listen(server_fd, 5) < 0) {
        perror("Listen failed");
        exit(1);
    }
    
    printf("[+] Secure Note Server running on port %d\n", PORT);
    printf("[+] Connect with: nc localhost %d\n", PORT);
    
    while (1) {
        client_fd = accept(server_fd, (struct sockaddr*)&client_addr, &client_len);
        if (client_fd < 0) {
            perror("Accept failed");
            continue;
        }
        
        printf("[+] New connection from %s:%d\n", 
               inet_ntoa(client_addr.sin_addr), ntohs(client_addr.sin_port));
        
        if (fork() == 0) {
            close(server_fd);
            handle_client(client_fd);
            exit(0);
        }
        close(client_fd);
    }
    
    return 0;
}
