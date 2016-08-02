# UberScript

This python library provides an easy and safe way to let ordinary users
execute ansible playbooks as root.

# Theory of Operation

The developer writes a small python script (10-30 lines, mostly
definitions) which initializes UberScript. Following a method call the
library takes over, parses user-given arguments, validates their
contents and passes them on to a given ansible playbook via the ansible
python module. All parameters are checked for proper types (including
more complicated checks like domain-validity).

## Security

This library is a small-ish wrapper around pythons battle-tested [argparse](https://docs.python.org/2/library/argparse.html)
and the ansible api. Arguments are passed to argparse for evaluation.
All standard-types like integers are handled by the python standard
library. Special types like domains are implemented within UberScript.
Once argparse has finished UberScript relies on the ansible API to
execute the given playbook. All parameters are passed safely as variables.

Before parsing parameters UberScript executes itself as root via sudo.
Combined with a proper sudoers-config this ensures that the script has
not been copied somewhere else is unmodified.

# Script-Development

```python
#!/bin/env python2

import uberscript
import uberscript.types

uberscript.UberScript(
  playbook='add_domain.yml',
  parameters=[
    ('domain', 'd', {
      'help': 'this is the domain to add to your uberspace',
      'type': uberscript.types.domain,
    }),
  ],
).auto()
```

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

There is a small number of arguments added by UberScript:

| Name | Description |
| ---- | ----------- |
| `depends` | makes this argument depend on the presence of another one |

### Types

In general the type-argument is identical to the one supplied to the
python function [`add_argument()`](https://docs.python.org/2/library/argparse.html#type).
UberScript only adds a couple of special types, which can be used by
referencing the as `uberscript.types.<name>`.

| Name | Category | Description |
| ---- | -------- | ----------- |
| `domain` | normal | a domain with valid length, format and tld |
| `restricted_str` | factory | string which only allows certain characters given in regex-format (e.g. `a-z0-9`) |

All custom types fall into one of two categories: "normal" or "factory".
Normal types can be supplied just as they are: `'type': uberscript.types.domain`.
Factory types require additional parameters to work properly: `'type': uberscript.types.restricted_str('a-z0-9')`.

# Library-Development

This project uses python 2.7, because python 3.x is not supported by
ansible. It is tested using pytest. There are both unit and end-to-end
tests.

## Setup
To get a basic environment up and running, use the following commands:

```bash
virtualenv venv --python python2
source venv/bin/activate
pip install -r requirements.txt
```

## Tests
The functionality of this library can be tested using pytest:
`py.test uberscript`. New tests should be added to the `uberscript/test`-
directory.