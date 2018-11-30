import requests
import re
import json
import paramiko
import kubernetes.client
import openshift.client
import argparse

import requests.packages.urllib3
requests.packages.urllib3.disable_warnings()


class Avi(object):
    def __init__(self, host='127.0.0.1', username='admin', password=None, verify=False, out_dir=None):
        if password == None:
            raise Exception('Avi authentication account password not provided')
        self.export = None
        self.se_connections = []
        self.ctrl_connections = []
        self.k8s = []
        self.host = host
        self.username = username
        self.password = password
        self.out_dir = out_dir
        self.base_url = 'https://' + host
        self.session = requests.session()
        self.session.verify = verify

        self.login()
        self.backup()
        self.alerts()
        self.vs_inventory()
        self.cl_list = self._cluster_runtime()
        self.cc_list = self._ocp_connectors()

        for c in self.cc_list:
            self.k8s.append(K8s(k8s_cloud=c))

        for se_ip in self._se_local_addresses():
            self.se_connections.append(AviSE(se_ip, password=self.password, controllers=self.cl_list))

        for c_ip in self.cl_list:
            self.ctrl_connections.append(AviController(c_ip, password=self.password, controllers=self.cl_list))

    def vs_inventory(self):
        r = self._get('/api/virtualservice-inventory', params={'include_name': True})

    def alerts(self):
        r = self._get('/api/alert')

    def backup(self):
        r = self._get('/api/configuration/export', params={'full_system': True})
        self.export = r.json()

    def login(self):
        login_data = {'username': self.username, 'password': self.password}
        if not self._post('/login', data=login_data):
            raise Exception('Failed authenticating as %s:%s with host %s' % (self.username, self.password, self.host))

    def _cluster_runtime(self):
        ips = []
        cluster = self._get('/api/cluster/runtime')
        for node in cluster.json()['node_states']:
            ips.append(node['mgmt_ip'])
        return ips

    def _se_local_addresses(self):
        se_list = []
        inventory = self._get('/api/serviceengine-inventory', params={'include_name': True})
        securechannel = self._get('/api/securechannel')
        for sc in securechannel.json()['results']:
            for se in inventory.json()['results']:
                if sc['uuid'] == se['uuid']:
                    se_list.append(sc['local_ip'])
        return se_list

    def _ocp_connectors(self):
        cc_list = []
        clouds = self._get('/api/cloud')
        # for cloud in clouds.json()['results']:
        for cloud in self.export['Cloud']:
            if cloud['vtype'] == 'CLOUD_OSHIFT_K8S':
                cc_list.append(cloud)
        return cc_list

    def _get(self, uri, params=None):
        url = self._url(uri)
        return self._request('get', url, params=params)

    def _post(self, uri, params=None, data=None):
        url = self._url(uri)
        return self._request('post', url, params=params, data=data)

    def _url(self, uri):
        return self.base_url + uri

    def _write(self, path, data):
        try:
            with open(path, 'w') as fh:
                json.dump(data, fh)
        except Exception as e:
            print e.message

    def _request(self, method, url, params=None, data=None):
        _method = getattr(self.session, method)
        r = _method(url, params=params, data=data)
        try:
            r.raise_for_status()
        except Exception as e:
            print e.message
            return None
        try:
            data = r.json()
            m = re.match(self.base_url + '/(.*)', url)
            path = m.group(1).replace('/', '-') + '.json'
            # TODO Enable write below
            self._write(path, data)
        except ValueError:
            pass
        return r


class SSH_Base(object):
    def __init__(self, port=22, username=None, password=None):
        self._cmd_list = []
        self.local_ip = None
        self.local_port = port
        self.username = username
        self.password = password

    def run_commands(self):
        response_list = []
        for cmd in self._cmd_list:
            response_list.append(self._run_cmd(cmd, sudo=True))
        with open(self.local_ip + '.ssh.json', 'w') as fh:
            json.dump(response_list, fh)
        return response_list

    def _configure_ssh(self):
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.local_ip,
                    port=self.local_port,
                    username=self.username,
                    password=self.password)
        return ssh

    def _run_cmd(self, command, sudo=False):
        if sudo:
            command = 'sudo ' + command
        # TODO print is just for some feedback
        print command
        cmd = {'command': command}
        sin, sout, serr = self._ssh.exec_command(command, get_pty=True)
        if sudo:
            sin.write(self.password + '\n')
            sin.flush()
        cmd['response'] = sout.read()
        return cmd


class AviController(SSH_Base):
    def __init__(self, local_ip, port=22, username='admin', password=None, controllers=None):
        # TODO
        # Port: 5098 when running controller in a container
        super(AviController, self).__init__(port=port, username=username, password=password)
        self.local_ip = local_ip
        self.controllers = controllers
        self._cmd_list = ['hostname',
                          'ls -ail /opt/avi/log',
                          'ps -aux',
                          'top -b -o +%MEM | head -n 22',
                          '/opt/avi/scripts/taskqueue.py -s',
                          # TODO sort out the cc log name from the config
                          # 'grep "pending changes" /opt/avi/log/cc_agent_Default-Cloud.log',
                          'df -h']
        self._ssh = self._configure_ssh()
        self.command_list = self.run_commands()
        for p in self.ping_controllers():
            self.command_list.append(p)
        self._ssh.close()

    def ping_controllers(self):
        ctrl_list = []
        for ip in self.controllers:
            if ip is not self.local_ip:
                ctrl_list.append(self._run_cmd('ping -c5 %s' % ip))
        with open(self.local_ip + '.ping.json', 'w') as fh:
            json.dump(ctrl_list, fh)
        return ctrl_list


class AviSE(SSH_Base):
    def __init__(self, local_ip, port=5097, username='admin', password=None, controllers=None):
        super(AviSE, self).__init__(port=port, username=username, password=password)
        self.local_ip = local_ip
        self.controllers = controllers
        self._cmd_list = ['hostname',
                          'docker info',
                          'iptables -nvL',
                          'iptables -nvL -t nat',
                          'ip route show table all',
                          'ifconfig',
                          'ip link',
                          'ip addr',
                          'sysctl -a',
                          'df -h',
                          'ls -ail /opt/avi/log',
                          'date',
                          'ntpq -p']
        self._ssh = self._configure_ssh()
        self.command_list = self.run_commands()
        for p in self.ping_controllers():
            self.command_list.append(p)
        self._ssh.close()

    def ping_controllers(self):
        ctrl_list = []
        for ip in self.controllers:
            ctrl_list.append(self._run_cmd('ping -c5 %s' % ip))
        with open(self.local_ip + '.ping.json', 'w') as fh:
            json.dump(ctrl_list, fh)
        return ctrl_list


class K8s(object):
    def __init__(self, k8s_cloud=None):
        self._kauth = kubernetes.client.Configuration()
        self._kauth.host = 'https://' + k8s_cloud['oshiftk8s_configuration']['master_nodes'][0]
        self._kauth.verify_ssl = False
        self._kauth.api_key['authorization'] = k8s_cloud['oshiftk8s_configuration']['service_account_token']
        self._kauth.api_key_prefix['authorization'] = 'Bearer'

        self._oauth = kubernetes.client.Configuration()
        self._oauth.host = 'https://' + k8s_cloud['oshiftk8s_configuration']['master_nodes'][0]
        self._oauth.verify_ssl = False
        self._oauth.api_key['authorization'] = k8s_cloud['oshiftk8s_configuration']['service_account_token']
        self._oauth.api_key_prefix['authorization'] = 'Bearer'

        self.v1Api = kubernetes.client.CoreV1Api(kubernetes.client.ApiClient(self._kauth))
        self.nodes = self._k8s_api(self.v1Api, 'list_node')
        self.services = self._k8s_api(self.v1Api, 'list_service_for_all_namespaces')
        self.serviceaccounts = self._k8s_api(self.v1Api, 'list_serviceaccount')

        self.oapi = openshift.client.OapiApi(openshift.client.ApiClient(self._oauth))
        self.projects = self._k8s_api(self.oapi, 'list_project')

    def _k8s_api(self, api, cmd):
        try:
            response = getattr(api, cmd)()
            flat = kubernetes.client.ApiClient().sanitize_for_serialization(response)
            with open('k8s' + cmd + '.json', 'w') as fh:
                json.dump(flat, fh)
            return response
        except Exception as e:
            print 'K8s exception with %s' % cmd
            print e.message


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller', type=str, default='127.0.0.1')
    parser.add_argument('--username', type=str, default='admin')
    parser.add_argument('--password', type=str, default=None)
    parser.add_argument('--output', type=str, default='')
    parser.add_argument('--infra_label', type=str, default='region=infra')
    parser.add_argument('--secure_channel_port', type=int, default=5097)
    args = parser.parse_args()

    avi = Avi(host=args.controller, username=args.username, password=args.password, out_dir=args.output)
