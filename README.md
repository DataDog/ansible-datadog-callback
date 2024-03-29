# ansible-datadog-callback

A callback to send Ansible events and metrics to Datadog.

## Requirements

Ansible >= 2.0 and Python packages listed in the `requirements.txt` file.

Ansible <= 1.9 is no longer supported by this callback. The latest compatible
version is tagged with `1.0.2`.

For Mac OS X users: If you're running an older version of OS-installed python (e.g. python 2.7.10), you may need to [upgrade](https://github.com/kennethreitz/requests/issues/3883#issuecomment-281182498) to a newer version of OpenSSL (`pip install pyopenssl idna`).

## Installation

1. Install dependencies by running `pip install -r requirements.txt`.
2. Copy `datadog_callback.py` to your playbook callback directory (by default
`callback_plugins/` in your playbook's root directory). Create the directory
if it doesn't exist.
3. You have 3 ways to set your API key. The callback will first use the
   environment variable, then the configuration file, then hostvars/vault.

##### Using environment variable

Set the environment variable `DATADOG_API_KEY`.

Optionally to send data to Datadog EU, you can set the environment
variable `DATADOG_SITE=datadoghq.eu`.

To send data to a custom URL you can set the environment
variable `DATADOG_URL=<custom URL>`.

##### Using a yaml file

Create a `datadog_callback.yml` file alongside `datadog_callback.py`,
and set its contents with your [API key](https://app.datadoghq.com/account/settings#api),
as following:

```
api_key: <your-api-key>

# optionally to send data to Datadog EU add the following setting
site: datadoghq.eu
# optionally to send data to a custom URL add the following setting
url: <custom URl>
```

You can specify a custom location for the configuration file using the
`ANSIBLE_DATADOG_CALLBACK_CONF_FILE` environment file.

For example:
```
ANSIBLE_DATADOG_CALLBACK_CONF_FILE=/etc/datadog/callback_conf.yaml ansible-playbook ...
```

##### Using ansible hostvars and vault

Alternatively you can use the hostvars of the host ansible is being run from (preferably in the vault file):
```
datadog_api_key: <your-api-key>

# Optionally to send data to Datadog EU add the following setting
datadog_site: datadoghq.eu

# Optionally to send data to a custom URL add the following setting
datadog_url: <custom URL>
```

3. Be sure to whitelist the plugin in your ansible.cfg
```
[defaults]
callback_whitelist = datadog_callback
```

You should start seeing Ansible events and metrics appear on Datadog when your playbook is run.

## Inventory hostnames vs Datadog hostnames

By default, the events reported for individual hosts use inventory hostnames
as the value for the event `host` tag. This can lead to problems when Ansible
inventory hostnames are different than hostnames detected by the Datadog Agent.
In this case, the events are going to be reported for a seemingly non-existent
host (the inventory hostname), which will then disappear after some time
of inactivity. There are several possible solutions in this case. Let's assume
that we have a host `some.hostname.com` which is detected as
`datadog.detected.hostname.com` by the Datadog Agent:

* Use Ansible [inventory aliases](https://docs.ansible.com/ansible/latest/user_guide/intro_inventory.html#inventory-aliases):
  * Original inventory file:
    ```
    [servers]
    some.hostname.com
    ```
  * Adjusted inventory file using alias:
    ```
    [servers]
    datadog.detected.hostname.com ansible_host=some.hostname.com
    ```
* Overwrite the `get_dd_hostname` method in `datadog_callback.py`:
  ```
  def get_dd_hostname(self, ansible_hostname):
     """ This function allows providing custom logic that transforms an Ansible
     inventory hostname to a Datadog hostname.
     """
     dd_hostname = ansible_hostname.replace("some.", "datadog.detected.")
     return dd_hostname
  ```

## Contributing to ansible-datadog-callback

1. Fork it
2. Create your feature branch (`git checkout -b my-new-feature`)
3. Commit your changes (`git commit -am 'Add some feature'`)
4. Push to the branch (`git push origin my-new-feature`)
5. Create new Pull Request

## Copyright

Copyright (c) 2015 Datadog, Inc. See LICENSE for further details.
