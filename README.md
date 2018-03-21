# ansible-datadog-callback

A callback to send Ansible events and metrics to Datadog.

## Requirements

Ansible >=2.0

The following python libraries are required on the Ansible server:

- [`datadogpy`](https://github.com/DataDog/datadogpy/)
- `pyyaml` (install with `pip install pyyaml`)

Ansible <=1.9 is no longer supported by this callback. The latest compatible
version is tagged with `1.0.2`.

## Installation

Once the required libraries (see above) have been installed on the server:

1. Copy `datadog_callback.py` to your playbook callback directory (by default
`callback_plugins/` in your playbook's root directory). Create the directory
if it doesn't exist.
2. You have 3 ways to set your API key. The callback will first use the
   environment variable, then the configuration file, then hostvars/vault.

##### Using environment variable

Set the environment variable `DATADOG_API_KEY`.

##### Using a yaml file

Create a `datadog_callback.yml` file alongside `datadog_callback.py`,
and set its contents with your [API key](https://app.datadoghq.com/account/settings#api),
as following:

```
api_key: <your-api-key>
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
```

3. Be sure to whitelist the plugin in your ansible.cfg
```
[defaults]
callback_whitelist = datadog_callback
```

You should start seeing Ansible events and metrics appear on Datadog when your playbook is run.

## Contributing to ansible-datadog-callback

1. Fork it
2. Create your feature branch (`git checkout -b my-new-feature`)
3. Commit your changes (`git commit -am 'Add some feature'`)
4. Push to the branch (`git push origin my-new-feature`)
5. Create new Pull Request

## Copyright

Copyright (c) 2015 Datadog, Inc. See LICENSE for further details.
