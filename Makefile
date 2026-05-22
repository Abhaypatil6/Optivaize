.PHONY: install eval run demo

install:
	pip install -r requirements.txt

eval:
	python -m eval.run_eval

run:
	python main.py

demo:
	python main.py --demo
