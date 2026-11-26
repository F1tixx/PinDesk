PYTHON ?= python3

.PHONY: run test compile install uninstall clean

run:
	$(PYTHON) pindesk.py

test:
	$(PYTHON) -m unittest discover -v

compile:
	$(PYTHON) -m py_compile pindesk.py test_portable_launcher.py

install:
	bash install.sh

uninstall:
	bash uninstall.sh

clean:
	rm -rf __pycache__
