.PHONY: install test run fetch backtest optimize

install:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

test:
	PYTHONPATH=. python -m pytest tests/ -q

run:
	uvicorn app.api.main:app --host 0.0.0.0 --port 8000

fetch:
	PYTHONPATH=. python -m scripts.fetch_history --days 60

backtest:
	PYTHONPATH=. python -m scripts.backtest

optimize:
	PYTHONPATH=. python -m scripts.backtest --optimize
