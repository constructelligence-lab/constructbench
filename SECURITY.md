# Security policy

## Reporting a vulnerability

Please do not open a public issue. Use a
[private security advisory](https://github.com/constructelligence-lab/constructbench/security/advisories/new) with what you found,
how to reproduce it and the impact. This is a small open source project: there is no bounty and no guaranteed fix time, but reports
are taken seriously and credited if you wish.

## Running model-written code

The `+code` provider mode lets a model write Python that the harness runs. The restrictions (an isolated interpreter in a temporary
directory, an import allow-list, banned names such as `open`, `eval` and `exec`, and a timeout) are **best effort, not a security
boundary**. If you benchmark a model you do not trust, run ConstructBench inside a container or a throwaway virtual machine.

## API keys

Provider keys are read from environment variables. Never commit them, result files or logs that contain them.
