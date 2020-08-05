# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

.PHONY: usage convert clean

PACKAGE ?= rpm
BRANCH ?= c8s
DIR ?= git.centos.org
IMAGE_NAME := dist2src
CONTAINER_ENGINE ?= $(shell command -v podman 2> /dev/null || echo docker)

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
	$(CONTAINER_ENGINE) run -ti -v $(CURDIR)/dist2src:/usr/local/lib/python3.6/site-packages/dist2src:Z --entrypoint= $(OPTS) $(IMAGE_NAME) /bin/bash
