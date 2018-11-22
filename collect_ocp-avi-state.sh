#!/bin/bash
# Colors
RED='\e[31m'
GREEN='\e[32m'
RESET='\e[0m'
# Login
#
# oc get secret
# oc describe secret avi-token-kst4q 
#
# AVI_TOKEN='eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJrdWJlcm5ldGVzL3NlcnZpY2VhY2NvdW50Iiwia3ViZXJuZXRlcy5pby9zZXJ2aWNlYWNjb3VudC9uYW1lc3BhY2UiOiJkZWZhdWx0Iiwia3ViZXJuZXRlcy5pby9zZXJ2aWNlYWNjb3VudC9zZWNyZXQubmFtZSI6ImF2aS10b2tlbi1rc3Q0cSIsImt1YmVybmV0ZXMuaW8vc2VydmljZWFjY291bnQvc2VydmljZS1hY2NvdW50Lm5hbWUiOiJhdmkiLCJrdWJlcm5ldGVzLmlvL3NlcnZpY2VhY2NvdW50L3NlcnZpY2UtYWNjb3VudC51aWQiOiJjNDA2NjlmZC1lOTFiLTExZTgtOTk5YS0wMDUwNTY4ZmQ0YzYiLCJzdWIiOiJzeXN0ZW06c2VydmljZWFjY291bnQ6ZGVmYXVsdDphdmkifQ.ZgAozBufRVrYKLgLwrdqfM0Tv2-GfCG69Fi1fer-w6mFoO4iA8PjIWpFdpnmPEGMneyHbUX0letVdNwy4E7rY9_5962ip_yyUoW2wKCUSLwnW4yG-m0_xU_k777Nf5U7pEjtMI35fcESR5lMsq58ftn3Uk5SYTVCM17QfbJGWoI3T0cWgettFCMhcggvcurPtBNQUe73gg4W3MIGpgWEZuVnKJI5lLbYE4Z04HCixPtLi2XQtGXy7C9ysJltP0X3lEwWGusDWHV82sBlQ-gG0MXNohG9744YgRpE2TtyRl5YadHdNGYPPHvLsHhlaBVda0wIwkezV1fZqCt_gZ9e6A'
# oc login --insecure-skip-tls-verify=false --token=$AVI_TOKEN
#
# !!!
# Provided role can have limitted access rights check for not collected output 
# [root@ocp-server1 tmp.rAYZ3VYI8C-openshift-avi-state]# grep Forbidden *
# !!! 
#
oc whoami
# Initialize
TMP_DIR=$(mktemp -d --suffix=-openshift-avi-state)
DEST=$TMP_DIR
mkdir -p $DEST
read -p "Provide Avi Controller IP or FQDN: " AVI_CONTROLLER
read -p "Provide Avi Controller username: " AVI_USERNAME
read -s -p "Provide Avi Controller password: " AVI_PASSWORD
# Enable command logging
exec {BASH_XTRACEFD}>>$DEST/openshift-avinetworks-state.log
set -x
### OC DISCOVERY

# Data Capture
# 1,2 Total Number of Master Nodes and Worker Nodes
oc get nodes -o json &> $DEST/oc-get-nodes.json
oc get nodes -o wide --show-labels &> $DEST/oc-get-nodes.txt
oc describe nodes &> $DEST/oc-describe-nodes.txt
# 3 How many Services are deployed?
oc get svc -o wide --show-labels --all-namespaces &> $DEST/oc-get-svc-all-namespaces.txt
oc get svc --all-namespaces -o json &> $DEST/oc-get-svc-all-namespaces.json
oc describe svc --all-namespaces &> $DEST/oc-describe-svc-all-namespaces.txt
# 4 How many Routes/Ingress are deployed? (routes are in project namespace, routers are in (???))
oc get routes -o wide --show-labels --all-namespaces &> $DEST/oc-get-routes-all-namespaces.txt
oc get routes --all-namespaces -o json &> $DEST/oc-get-routes-all-namespaces.json
oc describe routes --all-namespaces &> $DEST/oc-describe-routes-all-namespaces.txt
# 5 How many Egress Pods are deployed?
oc get pods -o wide --show-labels --all-namespaces  &> $DEST/oc-get-pods-all-namespaces.txt
oc get pods --all-namespaces -o json &> $DEST/oc-get-pods-all-namespaces.json
#heavy collecting
#oc describe pods --all-namespaces
# 7 What is Openshift's EW Service Subnet?
oc get -o wide clusternetwork &> $DEST/oc-get-clusternetwork.txt
oc get clusternetwork -o json &> $DEST/oc-get-clusternetwork.json
# 8 Is avirole serviceaccount created?
oc get serviceaccounts --all-namespaces -o wide --show-labels &> $DEST/oc-get-serviceaccounts-all-namespaces.txt
oc get serviceaccounts --all-namespaces -o json &> $DEST/oc-get-serviceaccounts-all-namespaces.json
# 9 Does avirole have recommended permissions?
oc get role --all-namespaces -o wide &> $DEST/oc-get-role-all-namespaces.txt
oc get role --all-namespaces -o json &> $DEST/oc-get-role-all-namespaces.json
# 10 What is the current openshift version?
oc version &> $DEST/oc-version.txt
# 11 Share some of the routes/services yaml files
oc get svc -o yaml --all-namespaces &> $DEST/oc-get-svc-all-namespaces.yaml
oc get routes -o yaml --all-namespaces &> $DEST/oc-get-routes-all-namespaces.yaml
# 12 Any template that is used to create service/route?
oc get templates --all-namespaces -o wide &> $DEST/oc-get-templates-all-namespaces.txt
oc get templates --all-namespaces -o json &> $DEST/oc-get-templates-all-namespaces.json
# 13 How many projects are currently in use?
oc get projects --all-namespaces -o wide &> $DEST/oc-get-projects-all-namespaces.txt
oc get projects --all-namespaces -o json &> $DEST/oc-get-projects-all-namespaces.json

# 99 Events
timeout 15 oc get event -w &> $DEST/oc-get-event.txt
# 99 Status
oc status --all-namespaces &> $DEST/oc-status.txt
# 99 Storageclass
oc get storageclass --all-namespaces -o wide &> $DEST/oc-get-storageclass.txt
oc get storageclass --all-namespaces -o json  &> $DEST/oc-get-storageclass.json
# 99 Hostsubnet
oc get hostsubnet --all-namespaces -o wide --show-labels &> $DEST/oc-get-hostsubnet.txt
oc get hostsubnet --all-namespaces -o json &> $DEST/oc-get-hostsubnet.json
# 99 clusterrolebinding
oc get clusterrolebinding &> $DEST/oc-get-clusterrolebinding.txt

### SSH DISCOVERY
NODES_LIST=`oc get nodes | tail -n +2 | awk '{printf $1"\n"}'`
SSH_COLLECTION_CMDS="hostname;docker info;iptables -nvL;iptables -nvL -t nat;ip route show table all;ifconfig;ip link;ip addr;sysctl -a;df -h;date;ntpq -p;ping -c5 $AVI_CONTROLLER"
for NODE in $NODES_LIST; do
    ssh -oStrictHostKeyChecking=no $NODE $SSH_COLLECTION_CMDS &> $DEST/ssh-$NODE-info.txt
done

### AVI VANTAGE DISCOVERY
AVI_COOKIE=$DEST/avi_cookie
curl --connect-timeout 5 -i -s -k -X POST -c $AVI_COOKIE -b $AVI_COOKIE -H 'Content-type: application/json' -H 'X-Avi-Tenant: admin' -H "Referer: https://$AVI_CONTROLLER" -d'{"username":"'$AVI_USERNAME'","password":"'$AVI_PASSWORD'"}' https://$AVI_CONTROLLER/login &> /dev/null
curl -s -k -b $AVI_COOKIE -X GET -H "Referer: #https://$AVI_CONTROLLER" "https://$AVI_CONTROLLER/api/configuration/export?include_name=true&uuid_refs=true" &> $DEST/$AVI_CONTROLLER-configuration-export.json
curl -s -k -b $AVI_COOKIE -X GET -H "Referer: #https://$AVI_CONTROLLER" "https://$AVI_CONTROLLER/api/serviceengine-inventory?include_name" &> $DEST/$AVI_CONTROLLER-serviceengine-inventory.json
curl -s -k -b $AVI_COOKIE -X GET -H "Referer: #https://$AVI_CONTROLLER" "https://$AVI_CONTROLLER/api/alert?include_name" &> $DEST/$AVI_CONTROLLER-alert.json
curl -s -k -b $AVI_COOKIE -X GET -H "Referer: #https://$AVI_CONTROLLER" "https://$AVI_CONTROLLER/api/cluster/runtime" &> $DEST/$AVI_CONTROLLER-cluster-runtime.json


rm -f $AVI_COOKIE

# Compress
DEST_FILE=/tmp/openshift-avinetworks-state-$(date +%Y%m%d-%H%M%S).tar.gz
tar zcvf $DEST_FILE $TMP_DIR
echo -e "${GREEN}Data capture complete and archived in ${DEST_FILE}${RESET}"
# cleanup
# rm -r $TMP_DIR
