SERVICES = okll-xvfb okll-chromium okll-trader okll-dashboard

.PHONY: install start stop restart status logs logs-chromium logs-dashboard update

install:
	sudo bash deploy/install.sh

start:
	sudo systemctl start $(SERVICES)

stop:
	sudo systemctl stop okll-dashboard okll-trader okll-chromium okll-xvfb

restart:
	sudo systemctl restart okll-trader okll-dashboard

status:
	sudo systemctl status $(SERVICES)

logs:
	journalctl -fu okll-trader

logs-chromium:
	journalctl -fu okll-chromium

logs-dashboard:
	journalctl -fu okll-dashboard

update:
	git pull origin main
	.venv/bin/pip install -r requirements.txt -q
	sudo systemctl restart okll-trader okll-dashboard
