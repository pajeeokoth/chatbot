#!/usr/bin/env python3
"""CLI probe for CLU endpoint — lightweight checks without extra deps.

Usage: python tools/emit_clu_probe.py

It reads `mytravel/.env` for `CLU_ENDPOINT`, `CLU_API_KEY`, `CLU_PROJECT_NAME`,
and `CLU_DEPLOYMENT_NAME` and performs:
 - GET to the endpoint root
 - POST to the analyze-conversations path with a minimal payload

Prints status, content-type and a short body snippet for each request.
"""
import os
import json
import sys
import socket
from urllib import request, error
from urllib.parse import urljoin

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '..', 'mytravel', '.env')
    env_path = os.path.normpath(env_path)
    if load_dotenv:
        load_dotenv(env_path)
    return {
        'endpoint': os.getenv('CLU_ENDPOINT', ''),
        'key': os.getenv('CLU_API_KEY', ''),
        'project': os.getenv('CLU_PROJECT_NAME', ''),
        'deployment': os.getenv('CLU_DEPLOYMENT_NAME', ''),
    }


def probe_get(endpoint, key=None, timeout=8):
    if not endpoint:
        print('No CLU_ENDPOINT configured')
        return
    if not endpoint.startswith(('http://', 'https://')):
        url = 'https://' + endpoint + '/'
    else:
        url = endpoint if endpoint.endswith('/') else endpoint + '/'

    req = request.Request(url, method='GET')
    if key:
        req.add_header('Ocp-Apim-Subscription-Key', key)
    try:
        with request.urlopen(req, timeout=timeout) as r:
            ct = r.headers.get('Content-Type')
            body = r.read(2048)
            print('\nGET', url)
            print(' Status:', r.status)
            print(' Content-Type:', ct)
            try:
                print(' Body snippet:\n', body.decode('utf-8', errors='replace')[:1000])
            except Exception:
                print(' Body (binary):', body[:200])
    except error.HTTPError as he:
        try:
            body = he.read(2048)
        except Exception:
            body = b''
        print('\nGET', url)
        print(' HTTPError:', he.code)
        print(' Reason:', he.reason)
        print(' Content-Type:', getattr(he, 'headers', {}).get('Content-Type'))
        print(' Body snippet:\n', body.decode('utf-8', errors='replace')[:1000])
    except Exception as e:
        print('\nGET', url)
        print(' Error:', e)


def probe_post_analyze(endpoint, key, project, deployment, timeout=12):
    if not endpoint:
        print('No CLU_ENDPOINT configured')
        return
    if not endpoint.startswith(('http://', 'https://')):
        base = 'https://' + endpoint
    else:
        base = endpoint.rstrip('/')

    api_path = '/language/:analyze-conversations?api-version=2023-10-01'
    url = base + api_path

    payload = {
        'kind': 'Conversation',
        'analysisInput': {
            'conversationItem': {
                'id': '1', 'text': 'hello', 'modality': 'text', 'language': 'en', 'participantId': 'user'
            }
        },
        'parameters': {
            'projectName': project or '',
            'deploymentName': deployment or '',
            'stringIndexType': 'TextElement_V8'
        }
    }
    b = json.dumps(payload).encode('utf-8')
    req = request.Request(url, data=b, method='POST')
    req.add_header('Content-Type', 'application/json')
    if key:
        req.add_header('Ocp-Apim-Subscription-Key', key)

    try:
        with request.urlopen(req, timeout=timeout) as r:
            ct = r.headers.get('Content-Type')
            body = r.read(4096)
            print('\nPOST', url)
            print(' Status:', r.status)
            print(' Content-Type:', ct)
            try:
                print(' Body snippet:\n', body.decode('utf-8', errors='replace')[:2000])
            except Exception:
                print(' Body (binary):', body[:400])
    except error.HTTPError as he:
        try:
            body = he.read(4096)
        except Exception:
            body = b''
        print('\nPOST', url)
        print(' HTTPError:', he.code)
        print(' Reason:', he.reason)
        print(' Content-Type:', getattr(he, 'headers', {}).get('Content-Type'))
        print(' Body snippet:\n', body.decode('utf-8', errors='replace')[:2000])
    except Exception as e:
        print('\nPOST', url)
        print(' Error:', e)


def main():
    env = load_env()
    print('Using CLU endpoint:', env['endpoint'])
    probe_get(env['endpoint'], key=env['key'])
    probe_post_analyze(env['endpoint'], env['key'], env['project'], env['deployment'])


if __name__ == '__main__':
    main()
