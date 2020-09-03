# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

.PHONY: usage convert clean check-in-container

PACKAGE ?= rpm
BRANCH ?= c8s
DIR ?= git.centos.org
IMAGE_NAME := dist2src
CONTAINER_ENGINE ?= $(shell command -v podman 2> /dev/null || echo docker)
CONTAINER_CMD ?= /bin/bash
TEST_TARGET ?= ./tests
COLOR ?= yes

usage:
	@echo "Run 'make convert' to run the convert or 'make clean' to clean up things."
	@echo ""
	@echo "Set 'PACKAGE' to pick a package from git.centos.org/rpms. Defaults to '$(PACKAGE)'."
	@echo "Set 'BRANCH' to select the branch to convert. Defaults to '$(BRANCH)'."
	@echo "Set 'DIR' to specify a working directory. Defaults to '$(DIR)'."
	@echo "Set 'VERBOSE' to '-v' or '-vv' to increase verbosity."
	@echo ""
	@echo "Example:"
	@echo ""
	@echo "    PACKAGE=rpm BRANCH=c8s VERBOSE=-vv make convert"

# clean before running the convert, so that cloning works
convert: clean
	git clone https://git.centos.org/rpms/$(PACKAGE).git $(DIR)/rpms/$(PACKAGE)
	./dist2src.py $(VERBOSE) convert $(DIR)/rpms/$(PACKAGE):$(BRANCH) $(DIR)/src/$(PACKAGE):$(BRANCH)
	git -C $(DIR)/src/$(PACKAGE) log --oneline $(BRANCH)

clean:
	rm -rf $(DIR)/

build:
	$(CONTAINER_ENGINE) build -t $(IMAGE_NAME) .

run:
	$(CONTAINER_ENGINE) run \
		-ti --rm \
		-v $(CURDIR)/dist2src:/usr/local/lib/python3.6/site-packages/dist2src:Z \
		-v $(CURDIR)/packitpatch:/usr/bin/packitpatch:Z \
		-v $(CURDIR)/macros.packit:/usr/lib/rpm/macros.d/macros.packit:Z \
		--entrypoint= \
		-u $(shell id -u) \
		$(OPTS) \
		$(IMAGE_NAME) $(CONTAINER_CMD)

check:
	pytest-3 --color=$(COLOR) --showlocals -vv $(TEST_TARGET)

check-in-container:
	$(CONTAINER_ENGINE) run \
		-ti --rm \
		-v $(CURDIR)/dist2src:/usr/local/lib/python3.6/site-packages/dist2src:Z \
		-v $(CURDIR)/packitpatch:/usr/bin/packitpatch:Z \
		-v $(CURDIR)/macros.packit:/usr/lib/rpm/macros.d/macros.packit:Z \
		-v $(CURDIR)/tests_localhost:/tests_localhost:Z \
		--entrypoint= \
		-u $(shell id -u) \
		$(OPTS) \
		$(IMAGE_NAME) pytest --color=$(COLOR) --showlocals -vv /tests_localhost
