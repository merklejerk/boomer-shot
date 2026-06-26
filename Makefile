# Makefile for BoomerShot Screenshot & Snipping Tool

EXTENSION_UUID = boomer-shot@deluludev.com
EXTENSION_DIR = $(HOME)/.local/share/gnome-shell/extensions/$(EXTENSION_UUID)
BIN_DIR = $(HOME)/.local/bin

.PHONY: all install uninstall clean

all: compile-schemas

compile-schemas:
	glib-compile-schemas extension/schemas/

install: all
	@echo "Installing BoomerShot to $(EXTENSION_DIR)..."
	mkdir -p "$(EXTENSION_DIR)/schemas"
	mkdir -p "$(EXTENSION_DIR)/src"
	mkdir -p "$(BIN_DIR)"
	
	# Copy GNOME Shell extension files
	cp extension/metadata.json "$(EXTENSION_DIR)/"
	cp extension/extension.js "$(EXTENSION_DIR)/"
	cp extension/schemas/org.gnome.shell.extensions.boomer-shot.gschema.xml "$(EXTENSION_DIR)/schemas/"
	cp extension/schemas/gschemas.compiled "$(EXTENSION_DIR)/schemas/"
	
	# Copy Python editor files
	cp src/main.py "$(EXTENSION_DIR)/src/"
	cp src/editor.py "$(EXTENSION_DIR)/src/"
	cp src/canvas.py "$(EXTENSION_DIR)/src/"
	cp src/utils.py "$(EXTENSION_DIR)/src/"
	cp src/style.css "$(EXTENSION_DIR)/src/"
	
	# Compile GSettings schemas in the destination directory
	glib-compile-schemas "$(EXTENSION_DIR)/schemas"
	
	# Create binary launcher wrapper in user bin path
	@echo "Creating executable launcher in $(BIN_DIR)/boomer-shot..."
	echo '#!/bin/sh' > "$(BIN_DIR)/boomer-shot"
	echo 'exec python3 "$(EXTENSION_DIR)/src/main.py" "$$@"' >> "$(BIN_DIR)/boomer-shot"
	chmod +x "$(BIN_DIR)/boomer-shot"
	
	# Enable the extension
	@echo "Attempting to enable GNOME Shell extension..."
	-gnome-extensions enable $(EXTENSION_UUID)
	
	@echo "=========================================================="
	@echo "BoomerShot successfully installed!"
	@echo "1. If this is a new installation, you MUST log out and log"
	@echo "   back in for GNOME Shell to discover the extension."
	@echo "2. Once logged back in, the custom hotkeys will be active:"
	@echo "   - Super+Shift+S: Screenshot & Snipping Crop Tool"
	@echo "   - Super+Shift+W: Active Window Snipping Tool"
	@echo "=========================================================="

dev-setup:
	@echo "Setting up development environment with uv..."
	uv venv --python /usr/bin/python3 --system-site-packages --clear
	uv pip install pytest ruff

test:
	@echo "Running unit tests..."
	.venv/bin/pytest tests/

lint:
	@echo "Checking code style..."
	.venv/bin/ruff check src/ tests/

format:
	@echo "Formatting code style..."
	.venv/bin/ruff format src/ tests/

uninstall:
	@echo "Uninstalling BoomerShot..."
	-gnome-extensions disable $(EXTENSION_UUID)
	rm -rf "$(EXTENSION_DIR)"
	rm -f "$(BIN_DIR)/boomer-shot"
	@echo "BoomerShot uninstalled successfully."

clean:
	rm -f extension/schemas/gschemas.compiled
	rm -rf .venv
	find src/ -name "__pycache__" -exec rm -rf {} +

