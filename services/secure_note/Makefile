CC = gcc
CFLAGS = -Wall -Wextra -Wno-unused-parameter
TARGET = secure_note_server
SRCS = secure_note_server.c

.PHONY: all clean run

all: $(TARGET)

$(TARGET): $(SRCS)
	$(CC) $(CFLAGS) -o $(TARGET) $(SRCS)

clean:
	rm -f $(TARGET)
	rm -rf data/

run: $(TARGET)
	./$(TARGET)

debug: $(SRCS)
	$(CC) $(CFLAGS) -g -o $(TARGET) $(SRCS)
