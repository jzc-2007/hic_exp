.PHONY: setup start stop restart doctor test status compact-notes daily-status start-daily stop-daily

setup:
	bash scripts/setup.sh

start:
	bash scripts/start_all.sh

stop:
	bash scripts/stop_all.sh

restart:
	bash scripts/restart_all.sh

doctor:
	bash scripts/doctor.sh

test:
	bash scripts/run_tests.sh

status:
	python3 scripts/hicctl.py status

compact-notes:
	python3 scripts/hicctl.py compact-notes

daily-status:
	python3 scripts/daily_status_update.py --push

start-daily:
	bash scripts/start_daily_update.sh

stop-daily:
	bash scripts/stop_daily_update.sh
