# Prisma Cloud Tenant Locator Script

## Description

The `pcs-where-is.py` script uses the Prisma Cloud Support API to search for a tenant by Customer Name across stacks.

### Requirements

* An Access Key generated by a "LIGHT AGENT" Support User in each stack to inspect.

### Usage

Copy `config.py.orig` to `config.py` and edit it to include your access keys.

The `config.py` configuration file must exist in the curent working directory of the script.

Use `-h` to review all command-line parameters.

### Example

```bash
tkishel  ~ | Code | pcs-inspect | pcs-where-is ./pcs-where-is.py example

example found on API2 as Example Customer
	Customer ID:   12345
	Serial Number: 234567890
	Tenant ID:     3456790123456789
	Renewal Date:  2022-04-16 23:59:59
	Prisma ID:     4567890123456789
	Eval:          True
	Active:        True
	Credits:       10200
	Used Credits:  10200
```