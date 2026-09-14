SHELL := /bin/bash

PYTHON ?= python

IFACE ?= wlan0
UPSTREAM_HOST ?= 192.168.1.200
UPSTREAM_PORT ?= 1883

RUN ?=
SCENARIO ?=
REPEAT ?= 1
SAMPLE ?=
EVENT ?=
DETAIL ?=

NETEM := ./tools/netem_control.sh
RUN_DIR := evidence/$(RUN)
EVALUATION_DB := $(RUN_DIR)/evaluation.db
GATEWAY_DB := data/gateway.db


.PHONY: help status \
        baseline degraded clear \
        outage outage-start outage-end \
        prepare condition \
        storage event finish publish \
        reconcile-direct reconcile-gateway \
	recover gateway-status \
	check-upstream \
        prep-direct prep-gateway prep-degraded prep-out15 prep-out30


help:
	@echo "TM470 Raspberry Pi evaluation"
	@echo
	@echo "Network conditions:"
	@echo "  make status"
	@echo "  make baseline"
	@echo "  make degraded"
	@echo "  make outage"
	@echo "  make clear"
	@echo
	@echo "Formal outage:"
	@echo "  make outage-start RUN=<run-id>"
	@echo "  make outage-end   RUN=<run-id>"
	@echo
	@echo "Prepare a run:"
	@echo "  make prepare SCENARIO=<scenario> RUN=<run-id> REPEAT=<n>"
	@echo
	@echo "Short scenario preparation:"
	@echo "  make prep-direct   RUN=DIRECT-BASE-r1 REPEAT=1"
	@echo "  make prep-gateway  RUN=GATEWAY-BASE-r1 REPEAT=1"
	@echo "  make prep-degraded RUN=DEG-100MS-10LOSS-r1 REPEAT=1"
	@echo "  make prep-out15    RUN=OUT-15S-2HZ-r1 REPEAT=1"
	@echo "  make prep-out30    RUN=OUT-30S-5HZ-r1 REPEAT=1"
	@echo
	@echo "Evidence:"
	@echo "  make storage RUN=<run-id> SAMPLE=<sample-point>"
	@echo "  make event RUN=<run-id> EVENT=<name> DETAIL='<text>'"
	@echo "  make finish RUN=<run-id>"
	@echo "  make publish RUN=<run-id>"
	@echo
	@echo "Reconciliation:"
	@echo "  make reconcile-direct RUN=<run-id>"
	@echo "  make reconcile-gateway RUN=<run-id>"


status:
	@echo "Upstream route:"
	@ip route get "$(UPSTREAM_HOST)"
	@echo
	@echo "NetEm state:"
	@$(NETEM) show "$(IFACE)"


baseline:
	@echo "Applying baseline condition: no NetEm impairment"
	@if [ -n "$(RUN)" ] && [ -d "$(RUN_DIR)" ]; then \
		$(NETEM) clear "$(IFACE)" | tee "$(RUN_DIR)/tc_baseline.txt"; \
	else \
		$(NETEM) clear "$(IFACE)"; \
	fi


degraded:
	@echo "Applying degraded condition: 100 ms delay, 10% loss"
	@if [ -n "$(RUN)" ] && [ -d "$(RUN_DIR)" ]; then \
		$(NETEM) degraded "$(IFACE)" 100 10 | tee "$(RUN_DIR)/tc_degraded.txt"; \
	else \
		$(NETEM) degraded "$(IFACE)" 100 10; \
	fi


outage:
	@echo "Applying outage condition: 100% packet loss"
	@if [ -n "$(RUN)" ] && [ -d "$(RUN_DIR)" ]; then \
		$(NETEM) outage "$(IFACE)" | tee "$(RUN_DIR)/tc_outage.txt"; \
	else \
		$(NETEM) outage "$(IFACE)"; \
	fi


clear:
	@echo "Clearing NetEm"
	@if [ -n "$(RUN)" ] && [ -d "$(RUN_DIR)" ]; then \
		$(NETEM) clear "$(IFACE)" | tee "$(RUN_DIR)/tc_after_clear.txt"; \
	else \
		$(NETEM) clear "$(IFACE)"; \
	fi


outage-start:
	@test -n "$(RUN)" || (echo "ERROR: RUN is required"; exit 1)
	@test -d "$(RUN_DIR)" || (echo "ERROR: $(RUN_DIR) does not exist"; exit 1)
	@$(MAKE) outage RUN="$(RUN)"
	@$(PYTHON) -m tools.evaluation_evidence event \
		--run-dir "$(RUN_DIR)" \
		--event impairment_applied \
		--detail "100% packet loss on $(IFACE)"


outage-end:
	@test -n "$(RUN)" || (echo "ERROR: RUN is required"; exit 1)
	@test -d "$(RUN_DIR)" || (echo "ERROR: $(RUN_DIR) does not exist"; exit 1)
	@$(MAKE) clear RUN="$(RUN)"
	@$(PYTHON) -m tools.evaluation_evidence event \
		--run-dir "$(RUN_DIR)" \
		--event impairment_removed \
		--detail "NetEm cleared from $(IFACE)"


prepare:
	@test -n "$(SCENARIO)" || (echo "ERROR: SCENARIO is required"; exit 1)
	@test -n "$(RUN)" || (echo "ERROR: RUN is required"; exit 1)
	@$(PYTHON) -m tools.run_evaluation \
		--scenario "$(SCENARIO)" \
		--run-id "$(RUN)" \
		--repeat "$(REPEAT)" \
		--upstream-host "$(UPSTREAM_HOST)" \
		--upstream-port "$(UPSTREAM_PORT)" \
		--interface "$(IFACE)" \
		--fresh


condition:
	@test -n "$(SCENARIO)" || (echo "ERROR: SCENARIO is required"; exit 1)
	@case "$(SCENARIO)" in \
		DIRECT-BASE|GATEWAY-BASE) \
			$(MAKE) baseline RUN="$(RUN)" ;; \
		DEG-100MS-10LOSS) \
			$(MAKE) degraded RUN="$(RUN)" ;; \
		OUT-15S-2HZ|OUT-30S-5HZ) \
			$(MAKE) outage RUN="$(RUN)" ;; \
		*) \
			echo "ERROR: unknown scenario: $(SCENARIO)"; \
			exit 1 ;; \
	esac


storage:
	@test -n "$(RUN)" || (echo "ERROR: RUN is required"; exit 1)
	@test -n "$(SAMPLE)" || (echo "ERROR: SAMPLE is required"; exit 1)
	@$(PYTHON) -m tools.evaluation_evidence storage \
		--run-dir "$(RUN_DIR)" \
		--sample-point "$(SAMPLE)"


event:
	@test -n "$(RUN)" || (echo "ERROR: RUN is required"; exit 1)
	@test -n "$(EVENT)" || (echo "ERROR: EVENT is required"; exit 1)
	@$(PYTHON) -m tools.evaluation_evidence event \
		--run-dir "$(RUN_DIR)" \
		--event "$(EVENT)" \
		--detail "$(DETAIL)"


finish:
	@test -n "$(RUN)" || (echo "ERROR: RUN is required"; exit 1)
	@$(PYTHON) -m tools.evaluation_evidence finish \
		--run-dir "$(RUN_DIR)"


publish:
	@test -n "$(RUN)" || (echo "ERROR: RUN is required"; exit 1)
	@test -f "$(RUN_DIR)/impairment.json" || \
		(echo "ERROR: $(RUN_DIR)/impairment.json does not exist"; exit 1)
	@count=$$($(PYTHON) -c \
		"import json; d=json.load(open('$(RUN_DIR)/impairment.json')); print(d['message_count'])"); \
	rate=$$($(PYTHON) -c \
		"import json; d=json.load(open('$(RUN_DIR)/impairment.json')); print(d['message_rate_hz'])"); \
	path=$$($(PYTHON) -c \
		"import json; d=json.load(open('$(RUN_DIR)/impairment.json')); print(d['path'])"); \
	interval=$$($(PYTHON) -c \
		"import json; d=json.load(open('$(RUN_DIR)/impairment.json')); print(round(1000 / float(d['message_rate_hz'])))"); \
	if [ "$$path" = "direct" ]; then \
		host="$(UPSTREAM_HOST)"; \
		port="$(UPSTREAM_PORT)"; \
	else \
		host="localhost"; \
		port="1883"; \
	fi; \
	echo "Publishing $$count messages at $$rate msg/s"; \
	echo "Path: $$path -> $$host:$$port"; \
	$(PYTHON) -m tools.simulated_publisher \
		--run-id "$(RUN)" \
		--count "$$count" \
		--interval-ms "$$interval" \
		--host "$$host" \
		--port "$$port"

gateway-status:
	@sqlite3 data/gateway.db \
		"SELECT delivery_state, COUNT(*) FROM outbox_messages GROUP BY delivery_state;"


recover:
	@test -n "$(RUN)" || (echo "ERROR: RUN is required"; exit 1)
	@test -d "$(RUN_DIR)" || \
		(echo "ERROR: $(RUN_DIR) does not exist"; exit 1)
	@echo "Starting controlled recovery"
	@$(PYTHON) -m tools.evaluation_evidence event \
		--run-dir "$(RUN_DIR)" \
		--event recovery_started \
		--detail "Controlled recovery started"
	@if $(PYTHON) -m tools.run_controlled_recovery; then \
		$(PYTHON) -m tools.evaluation_evidence event \
			--run-dir "$(RUN_DIR)" \
			--event recovery_complete \
			--detail "Controlled recovery completed"; \
	else \
		$(PYTHON) -m tools.evaluation_evidence event \
			--run-dir "$(RUN_DIR)" \
			--event recovery_failed \
			--detail "Controlled recovery exited unsuccessfully"; \
		exit 1; \
	fi


reconcile-direct:
	@test -n "$(RUN)" || (echo "ERROR: RUN is required"; exit 1)
	@test -f "$(EVALUATION_DB)" || \
		(echo "ERROR: collector DB not found: $(EVALUATION_DB)"; exit 1)
	@$(PYTHON) -m tools.reconcile_run \
		--run-id "$(RUN)" \
		--evaluation-db "$(EVALUATION_DB)" \
		--direct


reconcile-gateway:
	@test -n "$(RUN)" || (echo "ERROR: RUN is required"; exit 1)
	@test -f "$(EVALUATION_DB)" || \
		(echo "ERROR: collector DB not found: $(EVALUATION_DB)"; exit 1)
	@test -f "$(GATEWAY_DB)" || \
		(echo "ERROR: gateway DB not found: $(GATEWAY_DB)"; exit 1)
	@$(PYTHON) -m tools.reconcile_run \
		--run-id "$(RUN)" \
		--gateway-db "$(GATEWAY_DB)" \
		--evaluation-db "$(EVALUATION_DB)"

check-upstream:
	@echo "Configured upstream:"
	@$(PYTHON) -c \
		"from src.config import UpstreamConfig; c=UpstreamConfig(); print(f'{c.broker_host}:{c.broker_port}')"
	@echo
	@echo "Route to expected Windows broker:"
	@ip route get "$(UPSTREAM_HOST)"


prep-direct:
	@$(MAKE) prepare \
		SCENARIO=DIRECT-BASE \
		RUN="$(RUN)" \
		REPEAT="$(REPEAT)"


prep-gateway:
	@$(MAKE) prepare \
		SCENARIO=GATEWAY-BASE \
		RUN="$(RUN)" \
		REPEAT="$(REPEAT)"


prep-degraded:
	@$(MAKE) prepare \
		SCENARIO=DEG-100MS-10LOSS \
		RUN="$(RUN)" \
		REPEAT="$(REPEAT)"


prep-out15:
	@$(MAKE) prepare \
		SCENARIO=OUT-15S-2HZ \
		RUN="$(RUN)" \
		REPEAT="$(REPEAT)"


prep-out30:
	@$(MAKE) prepare \
		SCENARIO=OUT-30S-5HZ \
		RUN="$(RUN)" \
		REPEAT="$(REPEAT)"
