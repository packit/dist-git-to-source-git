ANSIBLE_PYTHON := /usr/bin/python3
AP := ansible-playbook -vv -c local -i localhost, -e ansible_python_interpreter=$(ANSIBLE_PYTHON)
# "By default, Ansible runs as if --tags all had been specified."
# https://docs.ansible.com/ansible/latest/user_guide/playbooks_tags.html#special-tags
TAGS ?= all

# example:
# DEPLOYMENT=local make deploy TAGS=worker
deploy:
	$(AP) deploy.yml --tags $(TAGS)
