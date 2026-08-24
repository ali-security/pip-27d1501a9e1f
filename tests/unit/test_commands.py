import pytest
from mock import patch

from pip._internal.cli.req_command import (
    IndexGroupCommand,
    RequirementCommand,
    SessionCommandMixin,
)
from pip._internal.commands import commands_dict, create_command

# These are the expected names of the commands whose classes inherit from
# IndexGroupCommand.
EXPECTED_INDEX_GROUP_COMMANDS = ['download', 'install', 'list', 'wheel']


def check_commands(pred, expected):
    """
    Check the commands satisfying a predicate.
    """
    commands = [create_command(name) for name in sorted(commands_dict)]
    actual = [command.name for command in commands if pred(command)]
    assert actual == expected, 'actual: {}'.format(actual)


def test_commands_dict__order():
    """
    Check the ordering of commands_dict.
    """
    names = list(commands_dict)
    # A spot-check is sufficient to check that commands_dict encodes an
    # ordering.
    assert names[0] == 'install'
    assert names[-1] == 'help'


@pytest.mark.parametrize('name', list(commands_dict))
def test_create_command(name):
    """Test creating an instance of each available command."""
    command = create_command(name)
    assert command.name == name
    assert command.summary == commands_dict[name].summary


def test_session_commands():
    """
    Test which commands inherit from SessionCommandMixin.
    """
    def is_session_command(command):
        return isinstance(command, SessionCommandMixin)

    expected = ['download', 'install', 'list', 'search', 'uninstall', 'wheel']
    check_commands(is_session_command, expected)


def test_index_group_commands():
    """
    Test the commands inheriting from IndexGroupCommand.
    """
    def is_index_group_command(command):
        return isinstance(command, IndexGroupCommand)

    check_commands(is_index_group_command, EXPECTED_INDEX_GROUP_COMMANDS)

    # Also check that the commands inheriting from IndexGroupCommand are
    # exactly the commands with the --no-index option.
    def has_option_no_index(command):
        return command.parser.has_option('--no-index')

    check_commands(has_option_no_index, EXPECTED_INDEX_GROUP_COMMANDS)


@pytest.mark.parametrize('command_name', EXPECTED_INDEX_GROUP_COMMANDS)
@pytest.mark.parametrize(
    'disable_pip_version_check, no_index, expected_called',
    [
        # The fetch phase only runs when both disable_pip_version_check
        # and no_index are False.
        (False, False, True),
        (False, True, False),
        (True, False, False),
        (True, True, False),
    ],
)
@patch('pip._internal.cli.req_command.pip_self_version_check_fetch')
def test_index_group_pip_version_check(
    mock_version_check, command_name, disable_pip_version_check, no_index,
    expected_called,
):
    """
    Test whether the pre-body fetch runs when pip_version_check() is
    entered, for each of the IndexGroupCommand classes.
    """
    command = create_command(command_name)
    options = command.parser.get_default_values()
    options.disable_pip_version_check = disable_pip_version_check
    options.no_index = no_index
    # Return None so the emit half is a no-op.
    mock_version_check.return_value = None

    with command.pip_version_check(options, []):
        pass
    if expected_called:
        mock_version_check.assert_called_once()
    else:
        mock_version_check.assert_not_called()


@patch('pip._internal.cli.req_command.pip_self_version_check_emit')
@patch('pip._internal.cli.req_command.pip_self_version_check_fetch')
def test_index_group_fetch_runs_before_the_command_body(
    mock_fetch, mock_emit,
):
    """
    The index-querying half of the self-version check must run *before* the
    command body, and only the rendering half after it.

    Doing the lookup afterwards (CVE-2026-6357) means pip inspects the
    environment and imports/executes code that the command it just ran --
    ``pip install`` above all -- may have replaced.
    """
    calls = []
    mock_fetch.side_effect = lambda session, options: calls.append('fetch')
    mock_emit.side_effect = lambda upgrade_prompt: calls.append('emit')

    command = create_command('download')
    options = command.parser.get_default_values()
    options.disable_pip_version_check = False
    options.no_index = False

    with command.pip_version_check(options, []):
        calls.append('body')

    assert calls == ['fetch', 'body', 'emit']


@patch('pip._internal.cli.req_command.pip_self_version_check_emit')
@patch('pip._internal.cli.req_command.pip_self_version_check_fetch')
def test_index_group_emit_runs_when_the_command_body_raises(
    mock_fetch, mock_emit,
):
    """The prompt is still rendered when the command body blows up."""
    calls = []
    mock_fetch.side_effect = lambda session, options: calls.append('fetch')
    mock_emit.side_effect = lambda upgrade_prompt: calls.append('emit')

    command = create_command('download')
    options = command.parser.get_default_values()
    options.disable_pip_version_check = False
    options.no_index = False

    with pytest.raises(ValueError):
        with command.pip_version_check(options, []):
            raise ValueError('boom')

    assert calls == ['fetch', 'emit']


@patch('pip._internal.cli.req_command.pip_self_version_check_fetch')
def test_index_group_pip_version_check_survives_a_failing_fetch(
    mock_version_check,
):
    """
    A broken fetch must not take the command down with it.

    The fetch now happens before the command body, so an exception escaping
    it would stop the command from running at all.
    """
    mock_version_check.side_effect = RuntimeError('no network')

    command = create_command('download')
    options = command.parser.get_default_values()
    options.disable_pip_version_check = False
    options.no_index = False

    ran = []
    with command.pip_version_check(options, []):
        ran.append(True)

    assert ran == [True]
    mock_version_check.assert_called_once()


@patch('pip._internal.cli.req_command.pip_self_version_check_fetch')
def test_install_pip_version_check_skipped_when_pip_is_a_requirement(
    mock_version_check,
):
    """
    ``pip install pip`` must skip the self-version check entirely: the
    running pip may be replaced before the prompt would be rendered.
    """
    mock_version_check.return_value = None

    command = create_command('install')
    options = command.parser.get_default_values()
    options.disable_pip_version_check = False
    options.no_index = False

    with command.pip_version_check(options, ['pip']):
        pass
    mock_version_check.assert_not_called()

    with command.pip_version_check(options, ['pip==20.3.4']):
        pass
    mock_version_check.assert_not_called()

    with command.pip_version_check(options, ['PIP']):
        pass
    mock_version_check.assert_not_called()

    with command.pip_version_check(options, ['some-other-pkg', 'pip']):
        pass
    mock_version_check.assert_not_called()

    with command.pip_version_check(options, ['some-other-pkg']):
        pass
    mock_version_check.assert_called_once()


def test_requirement_commands():
    """
    Test which commands inherit from RequirementCommand.
    """
    def is_requirement_command(command):
        return isinstance(command, RequirementCommand)

    check_commands(is_requirement_command, ['download', 'install', 'wheel'])
