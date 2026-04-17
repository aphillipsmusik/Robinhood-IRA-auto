SERVICES = okll-xvfb okll-chromium okll-trader

.PHONY: install start stop restart status logs logs-chromium update

install:
	sudo bash deploy/install.sh

start:
	sudo systemctl start $(SERVICES)

stop:
	sudo systemctl stop okll-trader okll-chromium okll-xvfb

restart:
	sudo systemctl restart okll-trader

status:
	sudo systemctl status $(SERVICES)

logs:
	journalctl -fu okll-trader

logs-chromium:
	journalctl -fu okll-chromium

update:
	git pull origin main
	.venv/bin/pip install -r requirements.txt -q
	sudo systemctl restart okll-trader
