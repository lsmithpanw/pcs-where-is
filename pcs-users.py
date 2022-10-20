#!/usr/bin/env python3

import argparse
import sys
import os
import signal
import json
import time
import requests
import arrow

from datetime import datetime
from dateutil.tz import gettz

##########################################################################################
# Process arguments / parameters.
##########################################################################################

pc_parser = argparse.ArgumentParser(description='Who are tenant users and when have they last logged in?', prog=os.path.basename(__file__))

pc_parser.add_argument('TenantID')
pc_parser.add_argument('AppStack')
pc_parser.add_argument(
    '--ca_bundle',
    default=os.environ.get('CA_BUNDLE', None),
    type=str,
    help='(Optional) - Custom CA (bundle) file')
pc_parser.add_argument(
    '-d', '--debug',
    action='store_true',
    help='(Optional) Enable debugging')

args = pc_parser.parse_args()

DEBUG_MODE = args.debug

##########################################################################################
# Helpers.
##########################################################################################

def handler(signum, frame):
    print()
    exit(1)

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
    if api_response.ok:
        api_response = json.loads(api_response.content)
        token = api_response.get('token')
    else:
        output('API (%s) responded with an error\n%s' % (url, api_response.text))
        #sys.exit(1)
        return
    if DEBUG_MODE:
        output(action)
        output(url)
        output(requ_data)
        output(api_response)
        # output(token)
        output()
    return token

def execute(action, url, token, ca_bundle=None, requ_data=None):
    headers = {'Content-Type': 'application/json'}
    headers['x-redlock-auth'] = token
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
        return

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
            output('API (%s) responded with an error\n%s' % (endpoint, api_response.content))
            sys.exit(1)
    return result

def find_customer(stack, tenants, customer_id, url, ca_bundle, token):
    count = 0
    if not tenants:
        return count
    for customer in tenants:
        prisma_id = str(customer['prismaId'])
        if customer_id == prisma_id:
            output('Tenant ID %s found on %s as %s' % (customer_id, stack, customer['customerName']))
            if DEBUG_MODE:
                output(json.dumps(customer, indent=4))
            output('\tCustomer ID:   %s' % customer['customerId'])
            if 'marketplaceData' in customer['licenseDetails'] and customer['licenseDetails']['marketplaceData']:
                if 'serialNumber' in customer['licenseDetails']['marketplaceData']:
                    output('\tSerial Number: %s' % customer['licenseDetails']['marketplaceData']['serialNumber'])
                if 'tenantId' in customer['licenseDetails']['marketplaceData']:
                    output('\tTenant ID:     %s' % customer['licenseDetails']['marketplaceData']['tenantId'])
                if 'endTs' in customer['licenseDetails'] and customer['licenseDetails']['endTs']:
                    endDt = datetime.fromtimestamp(customer['licenseDetails']['endTs']/1000.0)
                    output('\tRenewal Date:  %s' % endDt)
            output('\tPrisma ID:     %s' % customer['prismaId'])
            output('\tEval:          %s' % customer['eval'])
            output('\tActive:        %s' % customer['active'])
            output('\tCredits:       %s' % customer['workloads'])
            usage_query = json.dumps({'customerName': customer['customerName'], 'timeRange': {'type':'relative', 'value': {'amount': 1, 'unit': 'month'}}})
            usage = execute('POST', '%s/_support/license/api/v1/usage/time_series' % url, token, ca_bundle, usage_query)
            if DEBUG_MODE:
                output(json.dumps(usage, indent=4))
            if usage and 'dataPoints' in usage and len(usage['dataPoints']) > 0:
                current_usage = usage['dataPoints'][-1]
                if 'counts' in current_usage and len(current_usage['counts']) > 0:
                    current_usage_count = sum(sum(c.values()) for c in current_usage['counts'].values())
                    output('\tUsed Credits:  %s' % current_usage_count)
            output()
            count += 1
            users_query = json.dumps({'customerName': customer['customerName']})
            users = execute('POST', '%s/v2/_support/user' % url, token, ca_bundle, users_query)
            if DEBUG_MODE:
                output(json.dumps(users, indent=4))
            if users:
                output('%-*s\t\t%-*s\t\t%s' % (21, 'Name', 33, 'Email address', 'Last Login'))
                for user in users:
                    lastLogin = ""
                    tz = gettz(user['timeZone'])
                    if user['lastLoginTs'] == -1:
                        lastLogin = 'Never'
                    else:
                        ar = arrow.Arrow.fromtimestamp(user['lastLoginTs']/1000, tz)
                        lastLogin = '%s - %s' % (ar.format('YYYY-MM-DD'), ar.humanize())
                    output('%-*s\t\t%-*s\t\t%s' % (21, user['displayName'], 33, user['email'], lastLogin))
    return count

##########################################################################################
## Main.
##########################################################################################

CONFIG = {}
try:
    from config import *
except ImportError:
    output('Error reading configuration file: verify config.py exists in the same directory as this script.')
    exit(1)

configured = False
for stack in CONFIG['STACKS']:
    if CONFIG['STACKS'][stack]['access_key'] != None:
        configured = True
        break
if not configured:
    output('Error reading configuration file: verify credentials for at least one stack.')
    exit(1)

if args.AppStack:
    configured = False
    for stack in CONFIG['STACKS']:
        if args.AppStack.lower() == stack.lower():
            if CONFIG['STACKS'][stack]['access_key'] is not None:
                configured = True
                break
    if not configured:
        output('Error reading configuration file: verify credentials for the specified stack %s.' % args.AppStack)
        exit(1)

if args.ca_bundle:
    CONFIG['CA_BUNDLE'] = args.ca_bundle

stack = args.AppStack
token = login(CONFIG['STACKS'][stack]['url'], CONFIG['STACKS'][stack]['access_key'], CONFIG['STACKS'][stack]['secret_key'], CONFIG['CA_BUNDLE'])
if (not token):
    output('Unable to login into %s' % stack)
    output()
    sys.exit(1)

tenants = execute('GET', '%s/_support/customer' % CONFIG['STACKS'][stack]['url'], token, CONFIG['CA_BUNDLE'])
customers = find_customer(stack, tenants, args.TenantID, CONFIG['STACKS'][stack]['url'], CONFIG['CA_BUNDLE'], token)
if customers == 0:
    output('No customer tenant found with ID %s in stack %s' % (args.TenantID, args.AppStack))
