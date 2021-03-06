from __future__ import absolute_import
from __future__ import print_function

import argparse
import getpass
import inspect
import os.path
import sys

import six

from .runners.ansiblerunner import AnsibleRunner
from .root import become_user, check_user
import paternoster.types


class Paternoster:
    def __init__(self,
                 runner_parameters,
                 parameters=None,
                 become_user=None, check_user=None,
                 success_msg=None,
                 description=None,
                 runner_class=AnsibleRunner,
                 ):
        if parameters is None:
            self._parameters = []
        else:
            self._parameters = parameters
        self._become_user = become_user
        self._check_user = check_user
        self._success_msg = success_msg
        self._description = description
        self._sudo_user = None
        self._runner = runner_class(**runner_parameters)

    def _find_param(self, fname):
        """ look for a parameter by either its short- or long-name """
        for param in self._parameters:
            if param['name'] == fname or param.get('short', None) == fname:
                return param

        raise KeyError('Parameter {0} could not be found'.format(fname))

    def _check_type(self, argParams):
        """ assert that an argument does not use a string type opposed to an restricted_str, else raise a ValueError """
        action_whitelist = ('store_true', 'store_false', 'store_const', 'append_const', 'count')
        action = argParams.get('action', 'store')

        if 'type' not in argParams and action not in action_whitelist:
            raise ValueError('a type must be specified for each user-supplied argument')

        type = argParams.get('type', str)
        is_str_type = inspect.isclass(type) and issubclass(type, six.string_types)

        if is_str_type and action not in action_whitelist:
            raise ValueError('restricted_str instead of str or unicode must be used for all string arguments')

    def _convert_type(sefl, argParams):
        param_type = argParams.pop('type', None)
        param_type_params = argParams.pop('type_params', {})

        if isinstance(param_type, str):
            if param_type == 'int':
                argParams['type'] = int
            elif param_type == 'str':
                argParams['type'] = str
            elif param_type.startswith('paternoster.types.'):
                type_clazz = getattr(sys.modules['paternoster.types'], param_type.rpartition('.')[2])
                argParams['type'] = type_clazz(**param_type_params)
            else:
                raise Exception('unknown type ' + param_type)
        elif param_type:
            argParams['type'] = param_type

    def _build_argparser(self):
        parser = argparse.ArgumentParser(
            add_help=False,
            description=self._description,
        )
        requiredArgs = parser.add_argument_group('required arguments')
        optionalArgs = parser.add_argument_group('optional arguments')

        optionalArgs.add_argument(
            '-h', '--help', action='help', default=argparse.SUPPRESS,
            help='show this help message and exit'
        )

        for param in self._parameters:
            argParams = param.copy()
            argParams.pop('depends_on', None)
            argParams.pop('positional', None)
            argParams.pop('short', None)
            argParams.pop('name', None)
            argParams.pop('prompt', None)
            argParams.pop('prompt_options', None)

            self._convert_type(argParams)
            self._check_type(argParams)

            if param.get('positional', False):
                paramName = [param['name']]
            else:
                paramName = ['-' + param['short'], '--' + param['name']]

            if param.get('required', False) or param.get('positional', False):
                if param.get('prompt'):
                    parser.error((
                        "'--{}' is required and can't be combined with prompt"
                    ).format(
                        param['name'],
                    ))
                requiredArgs.add_argument(*paramName, **argParams)
            else:
                optionalArgs.add_argument(*paramName, **argParams)

        optionalArgs.add_argument(
            '-v', '--verbose', action='count', default=0,
            help='run with a lot of debugging output'
        )

        return parser

    def _prompt_for_missing(self, argv, parser, args):
        """
        Return *args* after prompting the user for missing arguments.

        Prompts the user for arguments (`self._parameters`), that are missing
        from *args* (don't exist or are set to `None`). But only if they have
        the `prompt` key set to `True` or a non empty string.

        """
        # get parameter dictionaries for missing arguments
        missing_params = (
            param for param in self._parameters
            if param.get('prompt')
            and isinstance(param.get('prompt'), (bool, six.string_types))
            and getattr(args, param['name']) is None
        )

        # prompt for missing args
        prompt_data = {
            param['name']: self.get_input(param) for param in missing_params
        }

        # add prompt_data to new argv and return newly parsed arguments
        if prompt_data:
            argv = list(argv) if argv else sys.argv[1:]
            for name, value in prompt_data.items():
                argv.append('--{}'.format(name))
                argv.append(value)
            return parser.parse_args(argv)

        # return already parsed arguments
        else:
            return args

    def _check_arg_dependencies(self, parser, args):
        for param in self._parameters:
            param_given = getattr(args, param['name'], None)
            dependency_given = 'depends_on' not in param or getattr(args, param['depends_on'], None)

            if param_given and not dependency_given:
                parser.error(
                    'argument --{} requires --{} to be present.'.format(param['name'], param['depends_on'])
                )

    def check_user(self):
        if not self._check_user:
            return
        if not check_user(self._check_user):
            print('This script can only be used by the user ' + self._check_user, file=sys.stderr)
            sys.exit(1)

    def become_user(self):
        if not self._become_user:
            return

        try:
            self._sudo_user = become_user(self._become_user)
        except ValueError as e:
            print(e, file=sys.stderr)
            sys.exit(1)

    def auto(self):
        self.check_user()
        self.become_user()
        self.parse_args()
        status = self.execute()
        sys.exit(0 if status else 1)

    def parse_args(self, argv=None):
        parser = self._build_argparser()
        try:
            args = parser.parse_args(argv)
            args = self._prompt_for_missing(argv, parser, args)
            self._check_arg_dependencies(parser, args)
            self._parsed_args = args
        except ValueError as exc:
            print(exc, file=sys.stderr)
            sys.exit(3)

    def _get_runner_variables(self):
        if self._sudo_user:
            yield ('sudo_user', self._sudo_user)

        yield ('script_name', os.path.basename(sys.argv[0]))

        for name in vars(self._parsed_args):
            value = getattr(self._parsed_args, name)
            if six.PY2 and isinstance(value, str):
                value = value.decode('utf-8')
            yield ('param_' + name, value)

    def execute(self):
        status = self._runner.run(self._get_runner_variables(), self._parsed_args.verbose)
        if status and self._success_msg:
            print(self._success_msg)
        return status

    @staticmethod
    def prompt(text, no_echo=False):
        """
        Return user input from a prompt with *text*.

        If *no_echo* is set, :func:`getpass.getpass` is used to prevent echoing
        of the user input. Exits gracefully on keyboard interrupts (with return
        code 3).

        """
        try:
            if no_echo:
                user_input = getpass.getpass(text)
            else:
                try:
                    user_input = raw_input(text)  # Python 2
                except NameError:
                    user_input = input(text)  # Python 3
            return user_input
        except KeyboardInterrupt:
            sys.exit(3)

    @staticmethod
    def get_input(param):
        """
        Return user input for *param*.

        The `param['name']` item needs to be set. The text for the prompt is
        taken from `param['prompt']`, if available and a non empty string.
        Otherwise `param['name']` is used. Also you can set additional
        arguments in `param['prompt_options']`:

        :accept_empty: if `True`: allows empty input
        :confirm: if `True` or string: prompt user for confirmation
        :confirm_error: if string: used as confirmation error message
        :no_echo: if `True`: don't echo the user input on the screen
        :strip: if `True`: strips user input

        Raises:
            KeyError: if no `name` item is set for *param*.
            ValueError: if input and confirmation do not match.

        """
        name = param['name']
        prompt = param.get('prompt')
        options = param.get('prompt_options', {})
        confirmation_prompt = options.get('confirm')
        accept_empty = options.get('accept_empty')
        no_echo = options.get('no_echo')
        strip = options.get('strip')

        # set prompt
        if not isinstance(prompt, six.string_types):
            prompt = '{}: '.format(name.title())

        # set confirmation prompt
        ask_confirmation = (
            confirmation_prompt
            and isinstance(confirmation_prompt, (bool, six.string_types))
        )
        if not isinstance(confirmation_prompt, six.string_types):
            confirmation_prompt = 'Please confirm: '

        # get input
        while True:
            value = Paternoster.prompt(prompt, no_echo)
            if strip:
                value = value.strip()
            if value or accept_empty:
                break

        # confirm
        if ask_confirmation:
            confirmed_value = Paternoster.prompt(confirmation_prompt, no_echo)
            if value != confirmed_value:
                confirm_error = (
                    options.get('confirm_error')
                    or 'ERROR: input does not match its confirmation'
                )
                raise ValueError(confirm_error)

        return value
