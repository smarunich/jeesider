#!/usr/bin/env python

import paramiko
import logging
import os
import shutil
import tarfile
import tempfile
import json
import requests
import argparse
import kubernetes.client
import openshift.client
import requests.packages.urllib3
requests.packages.urllib3.disable_warnings()
import urllib3
urllib3.disable_warnings()

se_commands = ['df -h',
               'iptables -nvL',
               'sysctl -a',
               'ntpdate -q']

TMP_DIR = tempfile.mkdtemp()
logging.basicConfig(filename=TMP_DIR + '/collector.log', filemode='w', level=logging.DEBUG)

def clean_up():
    #with tarfile.open(TMP_DIR + '.tar.gz', 'w:gz') as fh:
    #    for root, dirs, files in os.walk(TMP_DIR):
    #        for f in files:
    #            fh.add(os.path.join(root, f))
    #shutil.rmtree(TMP_DIR)
    print 'TMP_DIR: %s' % TMP_DIR
    pass

def ssh_cmd(ssh, command, sudo=False, password=None):
    if sudo:
        command = 'sudo ' + command
    cmd = {'command': command}
    sin, sout, serr = ssh.exec_command(command, get_pty=True)
    if sudo:
        sin.write(password + '\n')
        sin.flush()
    cmd['response'] = sout.read()
    return cmd

def handle_k8s(api, cmd):
    filename = TMP_DIR + '/' + cmd + '.json'
    try:
        response = getattr(api, cmd)()
        flat = kubernetes.client.ApiClient().sanitize_for_serialization(response)
        with open(filename, 'w') as fh:
            json.dump(flat, fh)
        return response
    except:
        pass

def avi_find_se():
    r = session.get(base_url + '/api/serviceengine-inventory')
    r.raise_for_status()
    se_list = []
    for se in r.json()['results']:
        se_list.append({'name': se['config']['name'],
                        'ip': se['config']['mgmt_ip_address']['addr'],
                        'state': se['runtime']['oper_status']['state'],
                        'uuid': se['uuid']})
    with open(TMP_DIR + '/serviceengine-inventory.json', 'w') as fh:
        json.dump(r.json(), fh)

    r = session.get(base_url + '/api/securechannel')
    r.raise_for_status()
    for sc in r.json()['results']:
        for se in se_list:
            if sc['uuid'] == se['uuid']:
                se['local_ip'] = sc['local_ip']
    with open(TMP_DIR + '/securechannel.json', 'w') as fh:
        json.dump(r.json(), fh)

    return se_list

def avi_find_ssh_user(backup):
    ocp_cloud = avi_find_ocp(backup)
    r = session.get(base_url + ocp_cloud['oshiftk8s_configuration']['ssh_user_ref'])
    r.raise_for_status()
    if r.json()['count'] == 1:
        ssh_user_ref = r.json()['results'][0]
        for user in backup['CloudConnectorUser']:
            if user['uuid'] == ssh_user_ref['uuid']:
                return user

def avi_find_ocp(backup):
    ocp_cloud = None
    for cloud in backup['Cloud']:
        if cloud['vtype'] == 'CLOUD_OSHIFT_K8S':
            if ocp_cloud == None:
                ocp_cloud = cloud
            else:
                raise Exception('Multiple vtype CLOUD_OSHIFT_K8S clouds found! Exiting...')
    return ocp_cloud

def avi_backup():
    # Get the full backup and write it
    r = session.get(base_url + '/api/configuration/export', params=param_data)
    try:
        r.raise_for_status()
        backup = r.json()
    except Exception as e:
        logging.debug('api configuration export failed: %s' % e.message)
        raise e
    logging.info('avi export configuration successful')
    try:
        with open(TMP_DIR + '/backup.json', 'w') as fh:
            json.dump(backup, fh)
    except Exception as e:
        logging.debug('avi configuration export failed to write to file: %s' % e.message)
    logging.info('avi export configuration written successfully')
    return backup

def avi_login(args):
    global base_url
    global param_data
    global session

    base_url   = 'https://%s' % args.controller
    login_data = {'username': args.username, 'password': args.password}
    param_data = {'full_system': True}

    # Build the session object and verify connectivity / login details
    session = requests.session()
    session.verify = False
    r = session.post(base_url + '/login', data=login_data)
    try:
        r.raise_for_status()
    except Exception as e:
        logging.debug('api authentication failed: %s' % e.message)
        raise e
    logging.info('avi authentication successful')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller', type=str, default='127.0.0.1')
    parser.add_argument('--username', type=str, default='admin')
    parser.add_argument('--password', type=str, default=None)
    parser.add_argument('--infra_label', type=str, default='region=infra')
    parser.add_argument('--secure_channel_port', type=int, default=5097)
    args = parser.parse_args()

    logging.info('startup_args: %s' % args)
    avi_login(args)

    print 'Collecting Avi Controller backup'
    backup = avi_backup()
    print 'Finding the OCP Cloud Connector'
    ocp_cloud = avi_find_ocp(backup)
    #ssh_user = avi_find_ssh_user(backup)
    print 'Finding the available Service Engines'
    se_list = avi_find_se()

    # Build the k8s auth material
    cfg = kubernetes.client.Configuration()
    cfg.host = 'https://' + ocp_cloud['oshiftk8s_configuration']['master_nodes'][0]
    cfg.verify_ssl = False
    cfg.api_key['authorization'] = ocp_cloud['oshiftk8s_configuration']['service_account_token']
    cfg.api_key_prefix['authorization'] = 'Bearer'

    v1Api = kubernetes.client.CoreV1Api(kubernetes.client.ApiClient(cfg))

    print 'Collecting the K8s node descriptions'
    nodes = handle_k8s(v1Api, 'list_node')
    print 'Collecting the K8s service descriptions'
    services = handle_k8s(v1Api, 'list_service_for_all_namespaces')

    # Forbidden as this user:
    # nw = openshift.client.NetworkOpenshiftIoV1Api(kubernetes.client.ApiClient(cfg))
    # nw.list_cluster_network()
    # Forbidden as this user:
    # routeApi = openshift.client.RouteOpenshiftIoV1Api(kubernetes.client.ApiClient(cfg))
    # routeApi.list_route_for_all_namespaces()

    # Handle the in container / SE shell commands
    for se in se_list:
        try:
            print 'Connecting to SE: %s' % se['name']
            se['ssh'] = paramiko.SSHClient()
            se['ssh'].load_system_host_keys()
            se['ssh'].set_missing_host_key_policy(paramiko.AutoAddPolicy())
            se['ssh'].connect(se['local_ip'],
                              port=args.secure_channel_port,
                              username=args.username,
                              password=args.password)
            se['se_commands'] = []
            for command in se_commands:
                print '\tRunning command: %s' % command
                se['se_commands'].append(ssh_cmd(se['ssh'], command, sudo=True, password=args.password))
        finally:
            try:
                se['ssh'].close()
                del se['ssh']
            except KeyError:
                pass
    with open(TMP_DIR + '/se_list.json', 'w') as fh:
        json.dump(se_list, fh)

    clean_up()


if __name__ == '__main__':
    main()
