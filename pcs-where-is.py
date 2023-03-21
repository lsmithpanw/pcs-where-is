#!/usr/bin/env python3

""" Where? """

import argparse
import json
import os
import re
import signal
import sys
import time

from datetime import datetime, timedelta

import requests

from dateutil.tz import gettz

# pylint: disable=import-error
import arrow

##########################################################################################
# Process arguments / parameters.
##########################################################################################

pc_parser = argparse.ArgumentParser(description='Where is this Tenant? Who are its users and when did they last login?', prog=os.path.basename(__file__))

pc_parser.add_argument(
    'customer_name',
    type=str,
    help='*Required* Customer Name, or filename containg a (JSON) array of Customer Names')
pc_parser.add_argument(
    '--ca_bundle',
    default=os.environ.get('CA_BUNDLE', None),
    type=str,
    help='(Optional) - Custom CA (bundle) file')
pc_parser.add_argument(
    '-s', '--stack',
    default='',
    type=str,
    help='(Optional) - Limit search to a stack (defined in the config file)')
pc_parser.add_argument(
    '-c', '--cache',
    action='store_true',
    help='(Optional) Cache responses from the API (eight hour lifetime)')
pc_parser.add_argument(
    '-d', '--debug',
    action='store_true',
    help='(Optional) Enable debugging')
pc_parser.add_argument(
    '-u', '--users',
    action='store_true',
    help='(Optional) Enumerate tenant users and their last login time')
pc_parser.add_argument(
    '--sort',
    default='name',
    choices=['login', 'name'],
    help="(Optional) Sort tenant users by login or name (Default: 'name')")
args = pc_parser.parse_args()

DEBUG_MODE = args.debug

##########################################################################################
# Helpers.
##########################################################################################

def handler(_signum, _frame):
    print()
    sys.exit(1)

signal.signal(signal.SIGINT, handler)

def output(output_data=''):
    print(output_data)

##########################################################################################
# Helpers.
##########################################################################################

def login(login_url, access_key, secret_key, ca_bundle):
    action = 'POST'
    url = '%s/login' % login_url
    headers = {'Content-Type': 'application/json'}
    requ_data = json.dumps({'username': access_key, 'password': secret_key})
    api_response = requests.request(action, url, headers=headers, data=requ_data, verify=ca_bundle)
    auth_token = None
    if api_response.ok:
        api_response = json.loads(api_response.content)
        auth_token = api_response.get('token')
    else:
        output('API (%s) responded with an error\n%s' % (url, api_response.text))
    if DEBUG_MODE:
        output(action)
        output(url)
        output(requ_data)
        output(api_response)
        # output(auth_token)
        output()
    return auth_token

def execute(action, url, auth_token, ca_bundle=None, requ_data=None):
    headers = {'Content-Type': 'application/json'}
    headers['x-redlock-auth'] = auth_token
    api_response = requests.request(action, url, headers=headers, data=requ_data, verify=ca_bundle)
    result = None
    if api_response.status_code in [401, 429, 500, 502, 503, 504]:
        output('Exceptional API response code %d received from %s. Waiting and then retrying' % (api_response.status_code, url))
        for _ in range(1, 3):
            time.sleep(16)
            api_response = requests.request(action, url, headers=headers, verify=ca_bundle, data=requ_data)
            if api_response.ok:
                break # retry loop
    if api_response.status_code == 403:
        output('403 Unauthorized: check that credentials are valid and are authorized to access the API.')
        return result
    if DEBUG_MODE:
        output(action)
        output(url)
        output(requ_data)
        output(api_response.status_code)
        # output(api_response.text)
        output()
    if api_response.ok:
        try:
            result = json.loads(api_response.content)
        except ValueError:
            output('API (%s) responded with an error\n%s' % (url, api_response.content))
            sys.exit(1)
    return result

def define_usage(url, auth_token, ca_bundle, tenant, range):
    usage_query = json.dumps({'customerName': tenant['customerName'], 'timeRange': {'type':'relative','value': {'amount': 1,'unit': range}}})
    usage = execute('POST', '%s/_support/license/api/v1/usage/time_series' % url, auth_token, ca_bundle, usage_query)
    if DEBUG_MODE:
        output(json.dumps(usage, indent=4))
    if usage and 'dataPoints' in usage and len(usage['dataPoints']) > 0:
        current_usage = usage['dataPoints'][-1]
        if 'counts' in current_usage and len(current_usage['counts']) > 0:
            current_usage_count = sum(sum(c.values()) for c in current_usage['counts'].values())
            output('\tCredit snapshot, end of period (%s):  %s' % (range,current_usage_count))

def find_customer(stack_name, tenant_list, customer_name, url, ca_bundle, auth_token):
    count = 0
    if not tenant_list:
        return count
    customer_name_lower = customer_name.lower()
    for tenant in tenant_list:
        customer_lower = tenant['customerName'].lower()
        prisma_id = str(tenant['prismaId'])
        if tenant['licenseDetails']['marketplaceData'] is not None:
            tenant_id = str(tenant['licenseDetails']['marketplaceData']['tenantId'])
            serial_num = str(tenant['licenseDetails']['marketplaceData']['serialNumber'])
        if customer_name_lower in customer_lower or customer_name_lower in prisma_id or customer_name_lower in tenant_id or customer_name_lower in serial_num:
            output('%s found on %s as %s' % (customer_name, stack_name, tenant['customerName']))
            if DEBUG_MODE:
                output(json.dumps(tenant, indent=4))
            output('\tCustomer ID:   %s' % tenant['customerId'])
            if 'marketplaceData' in tenant['licenseDetails'] and tenant['licenseDetails']['marketplaceData']:
                if 'serialNumber' in tenant['licenseDetails']['marketplaceData']:
                    output('\tSerial Number: %s' % tenant['licenseDetails']['marketplaceData']['serialNumber'])
                if 'tenantId' in tenant['licenseDetails']['marketplaceData']:
                    output('\tTenant ID:     %s' % tenant['licenseDetails']['marketplaceData']['tenantId'])
                if 'endTs' in tenant['licenseDetails'] and tenant['licenseDetails']['endTs']:
                    end_dt = datetime.fromtimestamp(tenant['licenseDetails']['endTs']/1000.0)
                    output('\tRenewal Date:  %s' % end_dt)
            output('\tPrisma ID:     %s' % tenant['prismaId'])
            output('\tEval:          %s' % tenant['eval'])
            output('\tActive:        %s' % tenant['active'])
            output('\tCredits Available:       %s' % tenant['workloads'])
            define_usage(url, auth_token, ca_bundle, tenant, "day")
            define_usage(url, auth_token, ca_bundle, tenant, "month")
            define_usage(url, auth_token, ca_bundle, tenant, "year")

            output()
            if args.users:
                users_query = json.dumps({'customerName': tenant['customerName']})
                users = execute('POST', '%s/v2/_support/user' % url, auth_token, ca_bundle, users_query)
                if DEBUG_MODE:
                    output(json.dumps(users, indent=4))
                if users:
                    output('%-*s\t\t%-*s\t\t%s' % (25, 'Name', 33, 'Email Address', 'Last Login'))
                    output('%-*s\t\t%-*s\t\t%s' % (25, '----', 33, '-------------', '----------'))
                    if args.sort == 'login':
                        users = sorted(users, key=lambda u: u['lastLoginTs'], reverse=True)
                    for user in users:
                        last_login = ''
                        time_zone = gettz(user['timeZone'])
                        if user['lastLoginTs'] == -1:
                            last_login = 'Never'
                        else:
                            arrow_time = arrow.Arrow.fromtimestamp(user['lastLoginTs']/1000, time_zone)
                            last_login = '%s - %s' % (arrow_time.format('YYYY-MM-DD'), arrow_time.humanize())
                        output('%-*s\t\t%-*s\t\t%s' % (25, user['displayName'], 33, user['email'], last_login))
            count += 1
    output()
    return count

##########################################################################################
## Main.
##########################################################################################

CONFIG = {}
try:
    # pylint: disable=wildcard-import
    from config import *
except ImportError:
    output('Error reading configuration file: verify config.py exists in the same directory as this script.')
    sys.exit(1)

configured = False
for stack in CONFIG['STACKS']:
    if CONFIG['STACKS'][stack]['access_key'] is not None:
        configured = True
        break
if not configured:
    output('Error reading configuration file: verify credentials for at least one stack.')
    sys.exit(1)

if args.stack:
    configured = False
    for stack in CONFIG['STACKS']:
        if args.stack.lower() == stack.lower():
            if CONFIG['STACKS'][stack]['access_key'] is not None:
                configured = True
                break
    if not configured:
        output('Error reading configuration file: verify credentials for the specified stack.')
        sys.exit(1)

if args.ca_bundle:
    CONFIG['CA_BUNDLE'] = args.ca_bundle

if os.path.isfile(args.customer_name):
    with open(args.customer_name, 'r', encoding='utf8') as f:
        CONFIG['CUSTOMERS'] = json.load(f)
else:
    CONFIG['CUSTOMERS'] = [args.customer_name]

for customer in CONFIG['CUSTOMERS']:
    found = 0
    for stack in CONFIG['STACKS']:
        if args.stack and args.stack.lower() != stack.lower():
            continue
        if CONFIG['STACKS'][stack]['access_key']:
            output('Checking: %s' % stack)
            output()
            token = login(CONFIG['STACKS'][stack]['url'], CONFIG['STACKS'][stack]['access_key'], CONFIG['STACKS'][stack]['secret_key'], CONFIG['CA_BUNDLE'])
            if not token:
                output('Skipping %s because of authentication failure.' % stack)
                output()
                continue
            customers_file_name = '/tmp/%s-customers.json' % re.sub(r'\W+', '', stack).lower()
            if os.path.isfile(customers_file_name):
                hours_ago = datetime.now() - timedelta(hours=8)
                customers_file_date = datetime.fromtimestamp(os.path.getctime(customers_file_name))
                if customers_file_date < hours_ago or args.cache is False:
                    if DEBUG_MODE:
                        output('Deleting cached stack file: %s' % customers_file_name)
                    os.remove(customers_file_name)
            if os.path.isfile(customers_file_name):
                with open(customers_file_name, 'r', encoding='utf8') as f:
                    if DEBUG_MODE:
                        output('Reading cached stack file: %s' % customers_file_name)
                    tenants = json.load(f)
            else:
                tenants = execute('GET', '%s/_support/customer' % CONFIG['STACKS'][stack]['url'], token, CONFIG['CA_BUNDLE'])
                if tenants and args.cache:
                    result_file = open(customers_file_name, 'w')
                    result_file.write(json.dumps(tenants))
                    result_file.close()
            found += find_customer(stack, tenants, customer, CONFIG['STACKS'][stack]['url'], CONFIG['CA_BUNDLE'], token)
    if found == 0:
        output('%s not found on any configured stack' % customer)
    output()
