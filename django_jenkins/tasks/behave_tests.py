"""
Build suite with behave tests
"""
import unittest
import sys

from optparse import make_option

import behave
from behave import configuration, runner
from os.path import dirname, abspath, join, isdir
from django.db.models import get_app
from django.conf import settings
from django_jenkins.tasks import BaseTask
from django.test import LiveServerTestCase


def get_features(app_module):
    app_dir = dirname(app_module.__file__)
    features_dir = abspath(join(app_dir, 'features'))
    if isdir(features_dir):
        return features_dir
    else:
        return None

def testCaseFactory(name):
    class DjangoBehaveTestCase(LiveServerTestCase):
        def __init__(self, features_dir, options):
            unittest.TestCase.__init__(self)
            self.features_dir = features_dir
            # sys.argv kludge
            # need to understand how to do this better
            # temporarily lose all the options etc
            # else behave will complain
            old_argv = sys.argv
            sys.argv = old_argv[:2]
            self.behave_config = behave.configuration.Configuration()
            sys.argv = old_argv
            # end of sys.argv kludge
            self.behave_config.paths = [features_dir]
            self.behave_config.format = ['pretty']

            self.behave_config.server_url = 'http://localhost:8081'

            self.behave_config.stdout_capture = options.get('behave_stdout_capture', False)
            self.behave_config.stderr_capture = options.get('behave_stderr_capture', False)

        def runTest(self, result=None):
            # run behave on a single directory
            print("run: features_dir=%s" % (self.features_dir))

            # from behave/__main__.py
            runner = behave.runner.Runner(self.behave_config)
            try:
                failed = runner.run()
            except behave.parser.ParserError as e:            
                sys.exit(str(e))
            except behave.configuration.ConfigError as e:
                sys.exit(str(e))

            if self.behave_config.show_snippets and runner.undefined:
                msg = u"\nYou can implement step definitions for undefined steps with "
                msg += u"these snippets:\n\n"
                printed = set()

                if sys.version_info[0] == 3:
                    string_prefix = "('"
                else:
                    string_prefix = u"(u'"

                for step in set(runner.undefined):
                    if step in printed:
                        continue
                    printed.add(step)

                    msg += u"@" + step.step_type + string_prefix + step.name + u"')\n"
                    msg += u"def impl(context):\n"
                    msg += u"    assert False\n\n"

                sys.stderr.write(behave.formatter.ansi_escapes.escapes['undefined'] + msg + behave.formatter.ansi_escapes.escapes['reset'])
                sys.stderr.flush()

            self.assertFalse(failed)

    DjangoBehaveTestCase.__name__ = name
    return DjangoBehaveTestCase

def make_test_suite(features_dir, app_label, options):
    return testCaseFactory(app_label)(features_dir=features_dir, options=options)

class Task(BaseTask):
    option_list = [
        make_option('--behave-stdout-capture',
                    action='store_true', dest='behave_stdout_capture',
            help='Do not capture stdout'),
        make_option('--behave-stderr-capture',
                    action='store_true', dest='behave_stderr_capture',
            help='Do not capture stderr'),

    ]

    def __init__(self, test_labels, options):
        super(Task, self).__init__(test_labels, options)
        self.options = options
        if not self.test_labels:
            if hasattr(settings, 'PROJECT_APPS') and not options['test_all']:
                self.test_labels = [app_name.split('.')[-1]
                                        for app_name in settings.PROJECT_APPS]

    def build_suite(self, suite, **kwargs):
        for label in self.test_labels:
            if '.' in label:
                print("Ignoring label with dot in: %s" % label)
                continue
            app = get_app(label)
            
            # Check to see if a separate 'features' module exists,
            # parallel to the models module
            features_dir = get_features(app)
            if features_dir is not None:
                # build a test suite for this directory
                features_test_suite = make_test_suite(features_dir, label, self.options)
                suite.addTest(features_test_suite)
