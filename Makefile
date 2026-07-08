# Makefile — duplicate PROD onto a no-Docker dev machine.
# Dump  : Postgres (pg_dump) + Chroma volume + media volume, pulled off the Pi.
# Restore: into native local Postgres + plain directories on disk.
#
#   make data-sync            # ONE-LINER: dump prod -> replace local db/chroma/media
#   make data-dump            # full prod snapshot -> dumps/
#   make data-restore-local   # restore db + extract chroma/media to disk
#
# BEFORE FIRST USE:
#   1. Set SSH_HOST to your Pi (tailscale name or ip). See below.
#   2. Set the compose project prefix — DB/CHROMA/MEDIA container + volume names
#      are derived from the docker-compose project name (defaults to the folder
#      name on the Pi). Set COMPOSE_PROJECT below to match.
#   3. Postgres db + user + password must match backend/.env.

# --- Remote (Pi) settings ---
SSH_HOST         ?= user@pi.tailXXXX.ts.net
COMPOSE_PROJECT  ?= app
DB_CONTAINER     ?= $(COMPOSE_PROJECT)-db-1
CHROMA_CONTAINER ?= $(COMPOSE_PROJECT)-chroma-1
CHROMA_VOL       ?= $(COMPOSE_PROJECT)_chroma_data
MEDIA_VOL        ?= $(COMPOSE_PROJECT)_media_data

# Leave DB_IP blank to auto-resolve the container IP over SSH (prevents drift).
# Set it explicitly (make DB_IP=172.18.0.9 ...) only to override.
DB_IP        ?=
DB_PORT      ?= 5432
# local end of the tunnel
LOCAL_PORT  ?= 15433
PGUSER      ?= postgres
PGPASSWORD  ?= postgres
PGDATABASE  ?= app

# --- LOCAL restore targets (native, no Docker) ---
LOCAL_DBURL       ?= postgresql://postgres:postgres@localhost:5432/$(PGDATABASE)
# == MEDIA_ROOT (BASE_DIR/media)
LOCAL_MEDIA_PATH  ?= ./backend/media
# your dev `chroma run --path` directory
LOCAL_CHROMA_PATH ?= ./.chroma

DUMP_DIR    := dumps
STAMP       := $(shell date +%Y%m%d_%H%M%S)
DUMP_FILE   := $(DUMP_DIR)/db_$(STAMP).dump

export PGPASSWORD

# Shell that prints the live DB container IP (honours an explicit DB_IP override).
RESOLVE_DB_IP = DB_IP="$(DB_IP)"; \
	if [ -z "$$DB_IP" ]; then \
	  DB_IP=$$(ssh $(SSH_HOST) "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $(DB_CONTAINER)" 2>/dev/null); \
	fi; \
	if [ -z "$$DB_IP" ]; then echo ">> Could not resolve $(DB_CONTAINER) IP (is the stack up?)"; exit 1; fi; \
	echo ">> Resolved $(DB_CONTAINER) -> $$DB_IP"

.PHONY: data-sync dumps-clean data-dump data-restore-local db-dump db-restore-local \
	vols-dump chroma-dump media-dump chroma-restore-local media-restore-local tunnel \
	test test-fast lint format

## ===== One-liner: pull prod and replace local =====
data-sync: dumps-clean data-dump data-restore-local
	@echo ">> data-sync complete: local db + chroma + media now mirror prod."

dumps-clean:
	@echo ">> Clearing $(DUMP_DIR)/"
	@rm -rf $(DUMP_DIR)

## ===== Full environment =====
data-dump: db-dump vols-dump
	@echo ">> Full prod snapshot complete -> $(DUMP_DIR)/"

data-restore-local: db-restore-local chroma-restore-local media-restore-local
	@echo ">> Local environment restored."

## ===== Postgres =====
db-dump:
	@mkdir -p $(DUMP_DIR)
	@$(RESOLVE_DB_IP); \
	echo ">> Opening tunnel localhost:$(LOCAL_PORT) -> $$DB_IP:$(DB_PORT) via $(SSH_HOST)"; \
	ssh -f -N -L $(LOCAL_PORT):$$DB_IP:$(DB_PORT) $(SSH_HOST); \
	TUNNEL_PID=$$(pgrep -f "ssh -f -N -L $(LOCAL_PORT):$$DB_IP:$(DB_PORT) $(SSH_HOST)"); \
	echo ">> Tunnel PID $$TUNNEL_PID"; sleep 1; \
	echo ">> Dumping $(PGDATABASE) -> $(DUMP_FILE)"; \
	pg_dump -Fc --no-owner --no-acl \
	-h localhost -p $(LOCAL_PORT) -U $(PGUSER) -d $(PGDATABASE) -f $(DUMP_FILE); \
	STATUS=$$?; \
	echo ">> Closing tunnel PID $$TUNNEL_PID"; kill $$TUNNEL_PID 2>/dev/null; \
	[ $$STATUS -eq 0 ] && echo ">> Done: $(DUMP_FILE)" || { echo ">> pg_dump FAILED ($$STATUS)"; exit $$STATUS; }

db-restore-local:
	@LATEST=$$(ls -1t $(DUMP_DIR)/*.dump 2>/dev/null | head -n1); \
	if [ -z "$$LATEST" ]; then echo "No .dump in $(DUMP_DIR)/"; exit 1; fi; \
	echo ">> Dropping & recreating $(PGDATABASE) on localhost"; \
	psql -h localhost -p 5432 -U $(PGUSER) -d postgres -v ON_ERROR_STOP=1 -c \
		"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$(PGDATABASE)' AND pid<>pg_backend_pid();" >/dev/null; \
	psql -h localhost -p 5432 -U $(PGUSER) -d postgres -v ON_ERROR_STOP=1 -c \
		"DROP DATABASE IF EXISTS \"$(PGDATABASE)\";"; \
	psql -h localhost -p 5432 -U $(PGUSER) -d postgres -v ON_ERROR_STOP=1 -c \
		"CREATE DATABASE \"$(PGDATABASE)\";"; \
	echo ">> Restoring $$LATEST into $(LOCAL_DBURL)"; \
	pg_restore --no-owner --no-acl -d "$(LOCAL_DBURL)" "$$LATEST"

## ===== File volumes (tarred off the Pi) =====
vols-dump: chroma-dump media-dump

chroma-dump:
	@mkdir -p $(DUMP_DIR)
	@echo ">> Stopping prod chroma for consistent snapshot"
	@ssh $(SSH_HOST) "docker stop $(CHROMA_CONTAINER) >/dev/null" || true
	@echo ">> Streaming $(CHROMA_VOL) -> $(DUMP_DIR)/chroma_data_$(STAMP).tgz"
	@ssh $(SSH_HOST) "docker run --rm -v $(CHROMA_VOL):/v:ro -w /v alpine tar czf - ." \
	> $(DUMP_DIR)/chroma_data_$(STAMP).tgz; STATUS=$$?; \
	echo ">> Restarting prod chroma"; ssh $(SSH_HOST) "docker start $(CHROMA_CONTAINER) >/dev/null" || true; \
	[ $$STATUS -eq 0 ] && echo ">> Done" || { echo ">> FAILED ($$STATUS)"; exit $$STATUS; }

media-dump:
	@mkdir -p $(DUMP_DIR)
	@echo ">> Streaming $(MEDIA_VOL) -> $(DUMP_DIR)/media_data_$(STAMP).tgz"
	@ssh $(SSH_HOST) "docker run --rm -v $(MEDIA_VOL):/v:ro -w /v alpine tar czf - ." \
	> $(DUMP_DIR)/media_data_$(STAMP).tgz

## ===== LOCAL restore to plain directories (NO Docker) =====
## Stop your local `chroma run` server before this — it must not hold the dir open.
chroma-restore-local:
	@C=$$(ls -1t $(DUMP_DIR)/chroma_data_*.tgz 2>/dev/null | head -n1); \
	if [ -z "$$C" ]; then echo "No chroma tarball in $(DUMP_DIR)/"; exit 1; fi; \
	echo ">> Extracting $$C -> $(LOCAL_CHROMA_PATH) (wiping existing)"; \
	mkdir -p "$(LOCAL_CHROMA_PATH)"; \
	rm -rf "$(LOCAL_CHROMA_PATH)"/*; \
	tar xzf "$$C" -C "$(LOCAL_CHROMA_PATH)"; \
	echo ">> Done. Restart your local chroma server."

media-restore-local:
	@M=$$(ls -1t $(DUMP_DIR)/media_data_*.tgz 2>/dev/null | head -n1); \
	if [ -z "$$M" ]; then echo "No media tarball in $(DUMP_DIR)/"; exit 1; fi; \
	echo ">> Extracting $$M -> $(LOCAL_MEDIA_PATH) (wiping existing)"; \
	mkdir -p "$(LOCAL_MEDIA_PATH)"; \
	rm -rf "$(LOCAL_MEDIA_PATH)"/*; \
	tar xzf "$$M" -C "$(LOCAL_MEDIA_PATH)"

## ===== Helper =====
tunnel:
	@$(RESOLVE_DB_IP); \
	echo ">> Tunnel localhost:$(LOCAL_PORT) -> $$DB_IP:$(DB_PORT) (Ctrl-C to close)"; \
	ssh -N -L $(LOCAL_PORT):$$DB_IP:$(DB_PORT) $(SSH_HOST)

## ===== Backend tooling =====
test:
	cd backend && uv run pytest

test-fast:
	cd backend && uv run pytest -n auto

lint:
	cd backend && uv run ruff check .
	cd frontend && npm run lint

format:
	cd backend && uv run ruff format .
