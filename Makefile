# M1: build the lab, observe and audit it. The netns lab needs root and FRRouting installed.
TTL ?= 2h
PY  ?= .venv/bin/python

.PHONY: help venv test lab-up lab-down lab-status lab-reap audit
help:
	@echo "venv | test | lab-up [TTL=2h DG_TUNNEL=gre|vxlan] | lab-down | lab-status | lab-reap | audit"

venv:
	python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"

test:
	.venv/bin/pytest -q

lab-up:
	sudo DG_TUNNEL=$${DG_TUNNEL:-gre} lab/netns/lab.sh up --ttl $(TTL)

lab-down:
	sudo lab/netns/lab.sh down

lab-status:
	sudo lab/netns/lab.sh status

lab-reap:
	sudo lab/netns/lab.sh reap

audit:
	sudo .venv/bin/driftgate audit
