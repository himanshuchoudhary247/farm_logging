PY=python3
VENV=venv
ACTIVATE=source $(VENV)/bin/activate

.PHONY: setup install api frontend run clean

setup:
	$(PY) -m venv $(VENV)
	$(ACTIVATE) && pip install --upgrade pip
	$(ACTIVATE) && pip install -r requirements.txt

install:
	$(ACTIVATE) && pip install -r requirements.txt

api:
	$(ACTIVATE) && PYTHONPATH=. uvicorn services.api_service.main:app --reload --port 8001

frontend:
	cd frontend && npm install && npm run build

run:
	@echo "Starting API (port 8001)..."
	@$(MAKE) api

clean:
	rm -rf $(VENV)
