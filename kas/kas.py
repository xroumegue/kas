# kas - setup tool for bitbake based projects
#
# Copyright (c) Siemens AG, 2017-2018
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""
    This module is the main entry point for kas, setup tool for bitbake based
    projects. In case of user errors (e.g. invalid configuration, repo fetch
    failure) KAS exits with error code 2, while exiting with 1 for internal
    errors. For details on error handling, see :mod:`kas.kasusererror`.
"""

import argparse
import atexit
import asyncio
import traceback
import logging
import signal
import sys
import os
from .kasusererror import KasUserError, CommandExecError

try:
    import colorlog
    HAVE_COLORLOG = True
except ImportError:
    HAVE_COLORLOG = False

from . import __version__, __file_version__, __compatible_file_version__
from . import plugins

__license__ = 'MIT'
__copyright__ = 'Copyright (c) Siemens AG, 2017-2018'

default_log_level = 'info'


def create_logger():
    """
        Setup the logging environment
    """
    log = logging.getLogger()  # root logger
    log.setLevel(logging.getLevelName(default_log_level.upper()))
    format_str = '%(asctime)s - %(levelname)-8s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    if HAVE_COLORLOG and os.isatty(2):
        cformat = '%(log_color)s' + format_str
        colors = {'DEBUG': 'reset',
                  'INFO': 'reset',
                  'WARNING': 'bold_yellow',
                  'ERROR': 'bold_red',
                  'CRITICAL': 'bold_red'}
        formatter = colorlog.ColoredFormatter(cformat, date_format,
                                              log_colors=colors)
    else:
        formatter = logging.Formatter(format_str, date_format)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    log.addHandler(stream_handler)
    return logging.getLogger(__name__)


def interruption():
    """
        Ignore SIGINT/SIGTERM in kas, let them be handled by our sub-processes
    """
    pass


def _atexit_handler():
    """
        Waits for completion of the event loop
    """
    try:
        loop = asyncio.get_running_loop()
        pending = asyncio.all_tasks(loop)
    except RuntimeError:
        # no running loop anymore, nothing to do
        return
    except AttributeError:
        # for Python < 3.7
        loop = asyncio.get_event_loop()
        pending = asyncio.Task.all_tasks(loop)
    if not loop.is_closed():
        # this code path is observed on older python versions (e.g. 3.6).
        # In case the loop is not yet closed, tasks still might throw
        # exceptions, but we are not interested in these as they are
        # likely due to the cancellation. By that, we simply drop them.
        try:
            loop.run_until_complete(asyncio.gather(*pending))
        except KasUserError:
            pass
        loop.close()


def kas_get_argparser():
    """
        Creates an argparser for kas with all plugins.
    """

    # Load plugins here so that the commands and arguments introduced by the
    # plugins can be seen by sphinx when it calls this function to build the
    # documentation
    plugins.load()

    parser = argparse.ArgumentParser(description='kas - setup tool for '
                                     'bitbake based project')

    verstr = '%(prog)s {} (configuration format version {}, ' \
        'earliest compatible version {})'.format(__version__, __file_version__,
                                                 __compatible_file_version__)
    parser.add_argument('--version', action='version', version=verstr)

    parser.add_argument('-d', '--debug',
                        action='store_const', const='debug', dest='log_level',
                        help='Enable debug logging (deprecated, use '
                             '--log-level debug).')

    parser.add_argument('-l', '--log-level',
                        choices=['debug', 'info', 'warning', 'error',
                                 'critical'],
                        default='%s' % (default_log_level),
                        help='Set log level (default: %s)' % default_log_level)

    subparser = parser.add_subparsers(help='sub command help', dest='cmd')

    for plugin in plugins.all():
        plugin_parser = subparser.add_parser(plugin.name, help=plugin.helpmsg)
        plugin.setup_parser(plugin_parser)

    return parser


def kas(argv):
    """
        The actual main entry point of kas.
    """
    create_logger()

    parser = kas_get_argparser()
    args = parser.parse_args(argv)

    if args.log_level:
        level_num = logging.getLevelName(args.log_level.upper())
        logging.getLogger().setLevel(level_num)

    logging.info('%s %s started', os.path.basename(sys.argv[0]), __version__)

    loop = asyncio.get_event_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, interruption)
    atexit.register(_atexit_handler)

    plugin_class = plugins.get(args.cmd)
    if plugin_class:
        plugin = plugin_class()
        plugin.run(args)
    else:
        parser.print_help()


def main():
    """
        The main function that operates as a wrapper around kas.
    """

    try:
        kas(sys.argv[1:])
    except CommandExecError as err:
        logging.error('%s', err)
        sys.exit(err.ret_code if err.forward else 2)
    except KasUserError as err:
        logging.error('%s', err)
        sys.exit(2)
    except Exception as err:
        logging.error('%s', err)
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
