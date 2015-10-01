import os.path
import time

import datadog
import yaml


class CallbackModule(object):
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
        except Exception, e:
            # We don't want Ansible to fail on an API error
            print 'Couldn\'t send event "{0}" to Datadog'.format(title)
            print e

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
                tags=self.default_tags,
                host=host,
            )
        except Exception, e:
            # We don't want Ansible to fail on an API error
            print 'Couldn\'t send metric "{0}" to Datadog'.format(metric)
            print e

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

    ### Ansible callbacks ###
    def runner_on_failed(self, host, res, ignore_errors=False):
        event_text = "$$$\n{0}[{1}]\n$$$\n".format(res['invocation']['module_name'], res['invocation']['module_args'])
        event_text += "$$$\n{0}\n$$$\n".format(res['msg'])
        self.send_task_event(
            'Ansible task failed on "{0}"'.format(host),
            alert_type='error',
            text=event_text,
            tags=['module:{0}'.format(res['invocation']['module_name'])],
            host=host,
        )

    def runner_on_ok(self, host, res):
        # Only send an event when the task has changed on the host
        if res.get('changed'):
            event_text = "$$$\n{0}[{1}]\n$$$\n".format(res['invocation']['module_name'], res['invocation']['module_args'])
            self.send_task_event(
                'Ansible task changed on "{0}"'.format(host),
                alert_type='success',
                text=event_text,
                tags=['module:{0}'.format(res['invocation']['module_name'])],
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

    def playbook_on_start(self):
        # Retrieve the playbook name from its filename
        self._playbook_name, _ = os.path.splitext(
            os.path.basename(self.playbook.filename))
        self.start_timer()
        host_list = self.playbook.inventory.host_list
        inventory = os.path.basename(os.path.realpath(host_list))
        self.send_playbook_event(
            'Ansible playbook "{0}" started by "{1}" against "{2}"'.format(
                self._playbook_name,
                self.playbook.remote_user,
                inventory),
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
            for metric, value in summary.iteritems():
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
