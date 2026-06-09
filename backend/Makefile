.PHONY: install test run fetch backtest optimize validate demo

install:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

test:
	PYTHONPATH=. python -m pytest tests/ -q

run:
	uvicorn app.api.main:app --host 0.0.0.0 --port 8000

demo:
	PYTHONPATH=. python -m scripts.demo_data
	PYTHONPATH=. python -m scripts.validate

fetch:
	PYTHONPATH=. python -m scripts.fetch_history --days 180

backtest:
	PYTHONPATH=. python -m scripts.backtest

optimize:
	PYTHONPATH=. python -m scripts.backtest --optimize

validate:
	PYTHONPATH=. python -m scripts.fetch_history --days 180
	PYTHONPATH=. python -m scripts.validate
