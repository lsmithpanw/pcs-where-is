#!/usr/bin/env python3

import argparse
import json
import os
import re
import requests
import sys
import time

from datetime import datetime, timedelta

##########################################################################################
# Process arguments / parameters.
##########################################################################################

pc_parser = argparse.ArgumentParser(description='What version is this app stack on?', prog=os.path.basename(__file__))


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
    '-d', '--debug',
    action='store_true',
    help='(Optional) Enable debugging')

args = pc_parser.parse_args()

DEBUG_MODE = args.debug

##########################################################################################
# Helpers.
##########################################################################################

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
        sys.exit(1)
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
        for _ in range(1, 3):
            time.sleep(16)
            api_response = requests.request(action, url, headers=headers, verify=ca_bundle, data=requ_data)
            if api_response.ok:
                break # retry loop
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
if (not configured):
    output('Error reading configuration file: verify credentials for at least one stack.')
    exit(1)

if args.stack:
    configured = False
    for stack in CONFIG['STACKS']:
        if args.stack.lower() == stack.lower():
            if CONFIG['STACKS'][stack]['access_key'] != None:
                 configured = True
                 break
    if (not configured):
        output('Error reading configuration file: verify credentials for the specified stack.')
        exit(1)

if args.ca_bundle:
    CONFIG['CA_BUNDLE'] = args.ca_bundle




for stack in CONFIG['STACKS']:
    if args.stack and args.stack.lower() != stack.lower():
        continue
    if CONFIG['STACKS'][stack]['access_key']:
        token = login(CONFIG['STACKS'][stack]['url'], CONFIG['STACKS'][stack]['access_key'], CONFIG['STACKS'][stack]['secret_key'], CONFIG['CA_BUNDLE'])
        
        version = execute('GET', '%s/version' % CONFIG['STACKS'][stack]['url'], token, CONFIG['CA_BUNDLE'])
        output('%s %s' % (CONFIG['STACKS'][stack]['url'], version))
               
