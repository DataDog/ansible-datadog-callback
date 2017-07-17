# ansible-datadog-callback

A callback to send Ansible events and metrics to Datadog.

## Requirements

Ansible >=1.1

The following python libraries are required on the Ansible server:

- [`datadogpy`](https://github.com/DataDog/datadogpy/)
- `pyyaml` (install with `pip install pyyaml`)

## Installation

Once the required libraries (see above) have been installed on the server:

1. Copy `datadog_callback.py` to your playbook callback directory (by default
`callback_plugins/` in your playbook's root directory). Create the directory
if it doesn't exist.
2. Create a `datadog_callback.yml` file alongside `datadog_callback.py`,
and set its contents with your [API key](https://app.datadoghq.com/account/settings#api),
as following:

```
api_key: <your-api-key>
```
alternatively (when using Ansible >=2.0) add:
```
datadog_api_key: <your-api-key>
```
to hostvars (preferably in the vault file) of the host ansible is being run from.

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
