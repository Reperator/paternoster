# Paternoster

Paternoster provides users with the ability to run certain tasks as
root or another user, while ensuring safety by providing a common
interface and battle tested parameter parsing/checking.

# Theory of Operation

The developer writes a small python script (10-30 lines, most of which
is a `dict`) which initializes Paternoster. Following a method call the
library takes over, parses user-given arguments, validates their
contents and passes them on to a given ansible playbook via the ansible
python module. All parameters are checked for proper types (including
more complicated checks like domain-validity).

## Security

This library is a small-ish wrapper around pythons battle-tested [argparse](https://docs.python.org/2/library/argparse.html)
and the ansible api. Arguments are passed to argparse for evaluation.
All standard-types like integers are handled by the python standard
library. Special types like domains are implemented within Paternoster.
Once argparse has finished Paternoster relies on the ansible API to
execute the given playbook. All parameters are passed safely as variables.

Before parsing parameters Paternoster executes itself as root via sudo.
Combined with a proper sudoers-config this ensures that the script has
not been copied somewhere else and is unmodified.

# Script-Development

A typical boilerplate for Paternoster looks like this:

```python
#!/bin/env python2.7

import paternoster
import paternoster.types

paternoster.Paternoster(
  runner_parameters={'playbook': '/opt/uberspace/playbooks/uberspace-add-domain.yml'},
  parameters=[
    ('domain', 'd', {
      'help': 'this is the domain to add to your uberspace',
      'type': paternoster.types.domain,
    }),
  ],
  success_msg='Your domain has been added successfully.',
).auto(become_root=True)
```

In this case the `auto()`-method-call executes all neccesary steps (become
root, parse arguments, execute playbook) at once. Whether the playbook
should be executed with root privileges, can be controlled by the `become_root`-
parameter. It is also possible to enforce that only the root user can start
the script by passing `check_root=True`. Note that these parameters are
exclusive.

## Parameters

All parameters are represented by a tuple of `('longname', 'shortname', {})`.
Long- and shortname are the respective `--long` and `-s`hort command line
arguments, followed by a dictionary supplying addtional values. Within
the dict all parameters to pythons [`add_argument()`-function](https://docs.python.org/2/library/argparse.html#the-add-argument-method) can be used.
Only the most important ones are listed here:

| Name | Description |
| ---- | ----------- |
| `help` | short text to describe the parameter in more detail |
| `type` | used to sanity-check the given value (e.g. "is this really a domain?") |
| `action` | can be used to create flag-arguments, when set to `store_true` or `store_false` |
| `required` | enforce the presence of certain argments |

There is a small number of arguments added by Paternoster:

| Name | Description |
| ---- | ----------- |
| `depends` | makes this argument depend on the presence of another one |

### Types

In general the type-argument is mostly identical to the one supplied to
the python function [`add_argument()`](https://docs.python.org/2/library/argparse.html#type).
To enforce a certain level of security, **all strings must be of the type
`restricted_str`**. It is not possible to add an string argument, which
does not have a defined set of characters. In addtion to `restricted_str`
Paternosters adds a couple of other special types, which can be used by
referencing them as `paternoster.types.<name>`, after importing
`paternoster.types`.

| Name | Category | Description |
| ---- | -------- | ----------- |
| `domain` | factory | a domain with valid length, format and tld |
| `restricted_str` | factory | string which only allows certain characters given in regex-format (e.g. `a-z0-9`). Additonally a `minlen` (default `1`) and `maxlen` (default `255`) can be passed to restrict the strings length. |
| `restricted_int` | factory | integer which can be restricted by a `minimum` and `maximum`-value, both of which are inclusive |

All custom types fall into one of two categories: "normal" or "factory":

* Normal types can be supplied just as they are: `'type': paternoster.types.domain`.
* Factory types require additional parameters to work properly: `'type': paternoster.types.restricted_str('a-z0-9')`.

### Custom Types

Just like Paternosters implemets a couple custom types, the developer of
a script can do the same. The argparse library is very flexible in this
regard, so it should even be possible to parse and validate x.509-certificates,
before passing their content to ansible, instead of their path.

For further details refer to the `types.py`-file within Paternoster or
the [documentation of argparse itself](https://docs.python.org/2/library/argparse.html#type).

### Dependencies

In some cases a parameter may need another one to function correctly. A
real-life example of this might be the `--namespace` parameter, which
depends on the `--mailserver` parameter in `uberspace-add-domain`. Such
a dependency can be expressed using the `depends`-option of a pararmeter:

```
parameters=[
  ('mailserver', 'm', {
    'help': 'add domain to the mailserver configuration',
    'action': 'store_true'
  }),
  ('namespace', 'e', {
    'help': 'use this namespace when adding a mail domain',
    'type': paternoster.types.restricted_str('a-z0-9'),
    'depends': 'mailserver',
  }),
]
```

At the moment there can only be a single dependency.

## Status Reporting

There are multiple ways to let the user know, what's going on:

### Failure

You can use the [`fail`-module](http://docs.ansible.com/ansible/fail_module.html)
to display a error message to the user. The `msg` option will be written
to stderr as-is, followed by an immediate exit of the script with exit-
code `1`.

### Success

To display a customized message when the playbook executes successfully
just set the `success_msg`-attribute of `Paternoster`, just as demonstrated
in the boilerplate above. The message will be written to stdout as-is.

### Progress Messages

If you want to inform the user about the current task your playbook is
executing, you can use the [`debug`-module](http://docs.ansible.com/ansible/debug_module.html).
All messages sent by this module are written to stdout as-is. Note that
only messages with the default `verbosity` value will be shown. All 
other verbosity-levels can be used for actual debugging.

## Variables

All arguments to the script are passed to ansible as variables with the
`param_`-prefix. This means that `--domain foo.com` becomes the variable
`param_domain` with value `foo.com`.

There are a few special variables to provide the playbook further
details about the environment it's in:

| Name | Description |
| ---- | ----------- |
| `sudo_user` | the user who executed the script originally. If the script is not configured to run as root, this variable does not exist. |
| `script_name` | the filename of the script, which is currently executed (e.g. `uberspace-add-domain`) |

# Library-Development

Most tasks (including adding new types) can be achieved by writing
scripts only. Therefore, the library does not need to be changed in most
cases. Sometimes it might be desirable to provide a new type or feature
to all other scripts. To fulfill these needs, the following section
outlines the setup and development process for library.

## Setup
To get a basic environment up and running, use the following commands:

```bash
virtualenv venv --python python2.7
source venv/bin/activate
python setup.py develop
```

This project uses python 2.7, because python 3.x is not yet supported by
ansible. All non-ansible code is tested with python 3.5 as well.

### Vagrant

Most features, where unit tests suffice can be tested using a virtualenv only. If your development
relies on the sudo-mechanism, you can spin up a [vagrant VM](https://vagrantup.com) which provides
a dummy `uberspace-add-domain`-script as well as the library-code in the
`/vagrant`-directory.

```bash
vagrant up
vagrant ssh
```

inside the host:

```
Last login: Wed Aug  3 17:23:02 2016 from 10.0.2.2
[vagrant@localhost ~]$ uberspace-add-domain -d a.com -v

PLAY [test play] ************** (...)
```

If you want to add your own scripts, just add the corresponding files in
`vagrant/files/playbooks` and `vagrant/files/scripts`. You can deploy it
using the `ansible-playbook vagrant/site.yml --tags scripts` command.
Once your script has been deployed, you can just edit the source file
to make further changes, as the file is symlinked, not copied.

## Tests

### Unit Tests

The core functionality of this library can be tested using the `tox`-
command. If only python 2.x or 3.x should be tested, the `-e` parameter
can be used, like so: `tox -e py35`, `tox -e py27`. New tests should be
added to the `paternoster/test`-directory.
Please refer to the [pytest-documentation](http://doc.pytest.org/) for
further details.

### System Tests

Some features (like the `become_root` function) require a correctly
setup linux environment. They can be tested using the provided ansible
playbooks in `vagrant/tests`.

The playbooks can be invoked using the `ansible-playbook`-command:

```
$ ansible-playbook vagrant/tests/test_variables.yml

PLAY [test script_name and sudo_user variables] ********************************

(...)

PLAY RECAP *********************************************************************
default                    : ok=7    changed=5    unreachable=0    failed=0
```

It is also possible to run all playbooks by executing `ansible-playbook vagrant/tests/test_*.yml`.
At some later point in development, the tests will be run automatically by
pytest or some other mechanism.

#### Boilerplate

A typical [ansible playbook](http://docs.ansible.com/ansible/playbooks.html)
for a system-test might look like this:

```yaml
- name: give this test a proper name
  hosts: all
  tasks:
    - include: drop_script.yml
      vars:
        ignore_script_errors: yes
        script_params: --some-parameter
        playbook: |
          - hosts: all
            tasks:
              - debug: msg="hello world"
        script: |
          #!/bin/env python2.7
          # some python code to test

    - assert:
        that:
          - "script.stdout_lines[0] == 'something'"
```

Most of the heavy lifting is done by the included `drop_script.yml`-file. It
creates the required python-script & playbook, executes it and stores the result
in the `script`-variable. After the execution, all created files are removed.
After the script has been executed, the [`assert`-module](http://docs.ansible.com/ansible/assert_module.html)
can be used to check the results.

There are several parameters to control the behaviour of `drop_script.yml`:

| Name | Optional | Description |
| ---- | -------- | ----------- |
| `script` | no | the **content** of a python script to save as `/usr/local/bin/uberspace-unittest` and execute |
| `playbook` | yes (default: empty) | the **content** of a playbook to save as `/opt/uberspace/playbooks/uberspace-unittest.yml` |
| `ignore_script_errors` | yes (default: `false`) | whether to continue even if python script has a non-zero exitcode |
| `script_params` | yes (default: empty) | command line parameters for the script (e.g. `"--domain foo.com"`) |
