FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    gcc \
    make \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY secure_note_server.c .
COPY Makefile .

RUN make

EXPOSE 4444

CMD ["./secure_note_server"]
