from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible import constants as C
from ansible.plugins.callback import CallbackBase
from ansible.utils.color import colorize, hostcolor

import os.path
import time

import datadog
import yaml

from pprint import pprint


class CallbackModule(CallbackBase):

    def __init__(self):
        # Read config and set up API client
        api_key, url = self._load_conf(os.path.join(os.path.dirname(__file__), "datadog_callback.yml"))
        datadog.initialize(api_key=api_key, api_host=url)

        self._playbook_name = None
        self._start_time = time.time()

    # Load parameters from conf file
    def _load_conf(self, file_path):
        conf_dict = {}
        with open(file_path, 'r') as conf_file:
            conf_dict = yaml.load(conf_file)

        return conf_dict.get('api_key', ''), conf_dict.get('url', 'https://app.datadoghq.com')

    # Send event to Datadog
    def _send_event(self, title, alert_type=None, text=None, tags=None, host=None, event_type=None, event_object=None):
        if tags is None:
            tags = []
        tags.extend(self.default_tags)
        priority = 'normal' if alert_type == 'error' else 'low'
        try:
            datadog.api.Event.create(
                title=title,
                text=text,
                alert_type=alert_type,
                priority=priority,
                tags=tags,
                host=host,
                source_type_name='ansible',
                event_type=event_type,
                event_object=event_object,
            )
        except Exception as e:
            # We don't want Ansible to fail on an API error
            pprint("Couldn\'t send event {0} to Datadog" % title)
            pprint(e)
            

    # Send event, aggregated with other task-level events from the same host
    def send_task_event(self, title, alert_type='info', text='', tags=None, host=None):
        # self.play is set by ansible
        if getattr(self, 'play', None):
            if tags is None:
                tags = []
            tags.append('play:{0}'.format(self.play.name))
        self._send_event(
            title,
            alert_type=alert_type,
            text=text,
            tags=tags,
            host=host,
            event_type='config_management.task',
            event_object=host,
        )

    # Send event, aggregated with other playbook-level events from the same playbook and of the same type
    def send_playbook_event(self, title, alert_type='info', text='', tags=None, event_type=''):
        self._send_event(
            title,
            alert_type=alert_type,
            text=text,
            tags=tags,
            event_type='config_management.run.{0}'.format(event_type),
            event_object=self._playbook_name,
        )

    # Send ansible metric to Datadog
    def send_metric(self, metric, value, tags=None, host=None):
        if tags is None:
            tags = []
        tags.extend(self.default_tags)
        try:
            datadog.api.Metric.send(
                metric="ansible.{0}".format(metric),
                points=value,
                tags=tags,
                host=host,
            )
        except Exception as e:
            # We don't want Ansible to fail on an API error
            pprint('Couldn\'t send metric "{0}" to Datadog'.format(metric))
            pprint(e)

    # Start timer to measure playbook running time
    def start_timer(self):
        self._start_time = time.time()

    # Get the time elapsed since the timer was started
    def get_elapsed_time(self):
        return time.time() - self._start_time

    # Default tags sent with events and metrics
    @property
    def default_tags(self):
        return ['playbook:{0}'.format(self._playbook_name)]

    @staticmethod
    def pluralize(number, noun):
        if number == 1:
            return "{0} {1}".format(number, noun)

        return "{0} {1}s".format(number, noun)

    # format helper for event_text
    @staticmethod
    def format_result(res):
        msg = "$$$\n{0}\n$$$\n".format(res['msg']) if res.get('msg') else ""
        module_name = 'undefined'

        if res.get('censored'):
            event_text = res.get('censored')
        elif not res.get('invocation'):
            event_text = msg
        else:
            event_text = "$$$\n{0}[{1}]\n$$$\n".format(res['invocation']['module_name'], res['invocation']['module_args'])
            event_text += msg
            module_name = 'module:{0}'.format(res['invocation']['module_name'])

        return event_text, module_name

    ### misc

    @staticmethod    
    def _getHost(result):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if delegated_vars:
            host = "[%s -> %s]" % (result._host.get_name(), delegated_vars['ansible_host'])
        else:
            host = "%s" % result._host.get_name()
        return host

    @staticmethod
    def _getModuleName(result):
        module_name = 'undefined'
        if 'invocation' in result._result and 'module_name' in result._result['invocation']:
            module_name = result._result['invocation']['module_name']

        return module_name

    ### Ansible callbacks ###

    def v2_runner_on_failed(self, result, ignore_errors=False):        
        if 'exception' in result._result:
            # extract just the actual error message from the exception text
            error = result._result['exception'].strip().split('\n')[-1]
            msg = "An exception occurred during task execution. The error was: %s" % error
        else:
            msg = "An error occured"
            
        host = self._getHost(result)
        module_name = self._getModuleName(result)
        self.send_task_event(
            'Ansible "{0}" failed on "{1}"'.format(result._task, host),
            alert_type='error',
            text=msg,
            tags=[module_name],
            host=host,
        )
                   

    def v2_runner_on_ok(self, result):
        self._clean_results(result._result, result._task.action)
        host = self._getHost(result)
        module_name = self._getModuleName(result)
        if result._task.action == 'include':
            return
        elif result._result.get('changed', False):
            msg = "changed : [%s]" % host
        else:
            msg = "changed : [%s]" % host
                        
        if result._task.loop and 'results' in result._result:
            self._process_items(result)
        else:
            self.send_task_event(
                'Ansible "{0}" changed on "{1}"'.format(result._task, host),
                alert_type='success',
                text=msg,
                tags=[module_name],
                host=host,                
            )


    def v2_runner_on_unreachable(self, result):
        host = self._getHost(result)
        self.send_task_event(
            'Ansible failed on unreachable host "{0}"'.format(host),
            alert_type='error',
            text="Host unreachable",
            host=host,
        )


    def v2_playbook_on_play_start(self, play):
        self._playbook_name = play.get_name()
        if not self._playbook_name:
            self._playbook_name = "PLAY"
        else:
            self._playbook_name = "%s" % self._playbook_name
        self.send_playbook_event(
            'Ansible playbook "{0}" started'.format(self._playbook_name),
            event_type='start'
        )            

    def v2_playbook_on_start(self):
        return

    def v2_playbook_on_stats(self, stats):
        hosts = sorted(stats.processed.keys())
        title = 'RECAP {0}'.format(self._playbook_name)
        for h in hosts:
            t = stats.summarize(h)
            
            msg = 'Recap :\n OK : %s, Changed : %s, Unreachable : %s, Failed : %s' % (t['ok'], t['changed'], t['unreachable'], t['failures'])
            self.send_playbook_event(
                title ,
                alert_type='info',
                text=msg,
                event_type='end'
            )
