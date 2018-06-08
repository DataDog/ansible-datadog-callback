from __future__ import absolute_import, print_function

import getpass
import logging
import os
import time

try:
    import datadog
    import yaml
    HAS_MODULES = True
except ImportError:
    HAS_MODULES = False


from ansible.plugins.callback import CallbackBase
from __main__ import cli


class CallbackModule(CallbackBase):
    def __init__(self):
        if not HAS_MODULES:
            self.disabled = True
            print('Datadog callback disabled: missing "datadog" and/or "yaml" python package.')
        else:
            self.disabled = False
            # Set logger level - datadog api and urllib3
            for log_name in ['requests.packages.urllib3', 'datadog.api']:
                self._set_logger_level(log_name)

        self._playbook_name = None
        self._start_time = time.time()
        self._options = None
        if cli:
            self._options = cli.options

        # self.playbook is set in the `v2_playbook_on_start` callback method
        self.playbook = None
        # self.play is set in the `playbook_on_play_start` callback method
        self.play = None

    # Set logger level
    def _set_logger_level(self, name, level=logging.WARNING):
        try:
            log = logging.getLogger(name)
            log.setLevel(level)
            log.propagate = False
        except Exception as e:
            # We don't want Ansible to fail on an API error
            print("Couldn't get logger - %s" % name)
            print(e)

    # Load parameters from conf file
    def _load_conf(self, file_path):
        conf_dict = {}
        if os.path.isfile(file_path):
            with open(file_path, 'r') as conf_file:
                conf_dict = yaml.load(conf_file)

        return os.environ.get('DATADOG_API_KEY', conf_dict.get('api_key', '')), conf_dict.get('url', 'https://app.datadoghq.com')

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
            print('Couldn\'t send event "{0}" to Datadog'.format(title))
            print(e)

    # Send event, aggregated with other task-level events from the same host
    def send_task_event(self, title, alert_type='info', text='', tags=None, host=None):
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
            print('Couldn\'t send metric "{0}" to Datadog'.format(metric))
            print(e)

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
            invocation = res['invocation']
            module_name = invocation.get('module_name', 'undefined')
            event_text = "$$$\n{0}[{1}]\n$$$\n".format(module_name, invocation.get('module_args', ''))
            event_text += msg
            if 'module_stdout' in res:
                # On Ansible v2, details on internal failures of modules are not reported in the `msg`,
                # so we have to extract the info differently
                event_text += "$$$\n{0}\n{1}\n$$$\n".format(
                    res.get('module_stdout', ''), res.get('module_stderr', ''))

        module_name_tag = 'module:{0}'.format(module_name)

        return event_text, module_name_tag

    ### Ansible callbacks ###
    def runner_on_failed(self, host, res, ignore_errors=False):
        # don't post anything if user asked to ignore errors
        if ignore_errors:
            return

        event_text, module_name_tag = self.format_result(res)
        self.send_task_event(
            'Ansible task failed on "{0}"'.format(host),
            alert_type='error',
            text=event_text,
            tags=[module_name_tag],
            host=host,
        )

    def runner_on_ok(self, host, res):
        # Only send an event when the task has changed on the host
        if res.get('changed'):
            event_text, module_name_tag = self.format_result(res)
            self.send_task_event(
                'Ansible task changed on "{0}"'.format(host),
                alert_type='success',
                text=event_text,
                tags=[module_name_tag],
                host=host,
            )

    def runner_on_unreachable(self, host, res):
        event_text = "\n$$$\n{0}\n$$$\n".format(res)
        self.send_task_event(
            'Ansible failed on unreachable host "{0}"'.format(host),
            alert_type='error',
            text=event_text,
            host=host,
        )

    # Implementation compatible with Ansible v2 only
    def v2_playbook_on_start(self, playbook):
        # On Ansible v2, Ansible doesn't set `self.playbook` automatically
        self.playbook = playbook

        playbook_file_name = self.playbook._file_name
        inventory = self._options.inventory

        self.start_timer()

        # Set the playbook name from its filename
        self._playbook_name, _ = os.path.splitext(
            os.path.basename(playbook_file_name))
        if isinstance(inventory, list):
            inventory = ','.join(inventory)
        self._inventory_name = ','.join([os.path.basename(os.path.realpath(name)) for name in inventory.split(',') if name])

    def v2_playbook_on_play_start(self, play):
        # On Ansible v2, Ansible doesn't set `self.play` automatically
        self.play = play
        if self.disabled:
            return

        # Read config and hostvars
        config_path = os.environ.get('ANSIBLE_DATADOG_CALLBACK_CONF_FILE', os.path.join(os.path.dirname(__file__), "datadog_callback.yml"))
        api_key, url = self._load_conf(config_path)

        # If there is no api key defined in config file, try to get it from hostvars
        if api_key == '':
            hostvars = self.play.get_variable_manager()._hostvars

            if not hostvars:
                print("No api_key found in the config file ({0}) and hostvars aren't set: disabling Datadog callback plugin".format(config_path))
                self.disabled = True
            else:
                try:
                    api_key = hostvars['localhost']['datadog_api_key']
                except Exception as e:
                    print('No "api_key" found in the config file ({0}) and "datadog_api_key" is not set in the hostvars: disabling Datadog callback plugin'.format(config_path))
                    self.disabled = True

        # Set up API client and send a start event
        if not self.disabled:
            datadog.initialize(api_key=api_key, api_host=url)

            self.send_playbook_event(
                'Ansible play "{0}" started in playbook "{1}" by "{2}" against "{3}"'.format(
                    self.play.name,
                    self._playbook_name,
                    getpass.getuser(),
                    self._inventory_name),
                event_type='start',
            )

    def playbook_on_stats(self, stats):
        total_tasks = 0
        total_updated = 0
        total_errors = 0
        error_hosts = []
        for host in stats.processed:
            # Aggregations for the event text
            summary = stats.summarize(host)
            total_tasks += sum([summary['ok'], summary['failures'], summary['skipped']])
            total_updated += summary['changed']
            errors = sum([summary['failures'], summary['unreachable']])
            if errors > 0:
                error_hosts.append((host, summary['failures'], summary['unreachable']))
                total_errors += errors

            # Send metrics for this host
            for metric, value in summary.items():
                self.send_metric('task.{0}'.format(metric), value, host=host)

        # Send playbook elapsed time
        self.send_metric('elapsed_time', self.get_elapsed_time())

        # Generate basic "Completed" event
        event_title = 'Ansible playbook "{0}" completed in {1}'.format(
            self._playbook_name,
            self.pluralize(int(self.get_elapsed_time()), 'second'))
        event_text = 'Ansible updated {0} out of {1} total, on {2}. {3} occurred.'.format(
            self.pluralize(total_updated, 'task'),
            self.pluralize(total_tasks, 'task'),
            self.pluralize(len(stats.processed), 'host'),
            self.pluralize(total_errors, 'error'))
        alert_type = 'success'

        # Add info to event if errors occurred
        if total_errors > 0:
            alert_type = 'error'
            event_title += ' with errors'
            event_text += "\nErrors occurred on the following hosts:\n%%%\n"
            for host, failures, unreachable in error_hosts:
                event_text += "- `{0}` (failure: {1}, unreachable: {2})\n".format(
                    host,
                    failures,
                    unreachable)
            event_text += "\n%%%\n"
        else:
            event_title += ' successfully'

        self.send_playbook_event(
            event_title,
            alert_type=alert_type,
            text=event_text,
            event_type='end',
        )
