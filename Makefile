PY=python3
VENV=venv
ACTIVATE=source $(VENV)/bin/activate

.PHONY: setup install-api install-app api app run clean

setup:
	$(PY) -m venv $(VENV)
	$(ACTIVATE) && pip install --upgrade pip
	$(ACTIVATE) && pip install -r requirements-api.txt
	$(ACTIVATE) && pip install -r requirements-app.txt

install-api:
	$(ACTIVATE) && pip install -r requirements-api.txt

install-app:
	$(ACTIVATE) && pip install -r requirements-app.txt

api:
	$(ACTIVATE) && PYTHONPATH=. uvicorn services.api_service.main:app --reload --port 8000

app:
	$(ACTIVATE) && streamlit run app.py

run:
	@echo "Starting API and Streamlit (two processes)..."
	@$(MAKE) -j 2 api app

clean:
	rm -rf $(VENV)
