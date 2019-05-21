#!/usr/bin/env python3
import json
import datetime
from datetime import date, timedelta
from dateutil import tz
from collections import defaultdict

import urllib.request
import urllib.error
import urllib.parse
import base64
import re

import argparse
import configparser
import sys

from requests.exceptions import RequestException
from pygerrit2 import GerritRestAPI, HTTPBasicAuth

from pprint import pprint


class ConfigParse:
    def __init__(self, args):
        self.projects_config = dict()
        self.conf = args.conf
        self.gerrit_config = args.gerrit_config
        self.DATE_RANGE = int(args.DATE_RANGE)

    def read_projects_config(self):
        """
        Read projects config file to determine Gerrit or Git users info.
        generate dictional of commiter type (Gerrit or Git) and list of Gerrit's email and Git's name, e.g.:
            'gerrit-users': ['user@couchbase.com', 'user2@couchbase.com'], ...
            'git-users': ['Git name', 'Git Name2'], ...
        """

        config = configparser.ConfigParser(allow_no_value=True)
        if config.read(self.conf):
            commit_user_group = config.sections()
        else:
            sys.exit(f'Error! Cannot parse {self.conf} file!')

        for c_user in commit_user_group:
            project_info = config.items(c_user)
            proj_names = [t[0] for t in project_info]
            self.projects_config[c_user] = proj_names

        return self.projects_config

    def read_gerrit_config(self):
        gerrit_config = configparser.ConfigParser()
        gerrit_config.read(self.gerrit_config)

        if 'main' not in gerrit_config.sections():
            print(
                'Invalid or unable to read config file "{}"'.format(
                    self.gerrit_config
                )
            )
            sys.exit(1)
        try:
            gerrit_url = gerrit_config.get('main', 'gerrit_url')
            user = gerrit_config.get('main', 'username')
            passwd = gerrit_config.get('main', 'password')
        except configparser.NoOptionError:
            print(
                'One of the options is missing from the config file: '
                'gerrit_url, username, password.  Aborting...'
            )
            sys.exit(1)

        # Initialize class to allow connection to Gerrit URL, determine
        # type of starting parameters and then find all related reviews
        auth = HTTPBasicAuth(user, passwd)
        rest = GerritRestAPI(url=gerrit_url, auth=auth)
        return auth, rest


class GenerateGerritCommits(ConfigParse):
    def __init__(self, projects_config):
        self.gerrit_user_emails = list()
        self.gerrit_user_accounts = defaultdict()
        self.projects_config = projects_config

    def get_gerrit_user_account(self):
        for c_group, c_emails in self.projects_config.items():
            if c_group == 'gerrit-users':
                for email in c_emails:
                    self.gerrit_user_emails.append(email)
        return self.gerrit_user_emails

    def generate_gerrit_user_name(self, gerrit_rest_obj):
        # Need to use gerrit api to get user account
        # generate data/user.json file
        rest = gerrit_rest_obj
        for u_email in self.gerrit_user_emails:
            try:
                query = u_email
                user_data = rest.get("/accounts/?suggest&q=%s" % query)
                for acc in user_data:
                    for key, value in acc.items():
                        if key == 'email':
                            user_email = value
                        elif key == 'name':
                            user_name = value
                    self.gerrit_user_accounts[user_email] = user_name
                # print(changes)
            except RequestException as err:
                print("Error: %s", str(err))
                sys.exit(1)
                #logger.error("Error: %s", str(err))
        return self.gerrit_user_accounts

    def get_time(self, input_time):
        indate = str(input_time).split('.')
        input_date = datetime.datetime.strptime(indate[0], '%Y-%m-%d %H:%M:%S')
        return input_date

    def get_gerrit_rest_data(self, auth, gerrit_rest_obj, date_range):
        currdate = datetime.datetime.utcnow()
        print(f'Date Range - {date_range}')
        print(f'From Date: {currdate}')
        print(f'To Date: {(currdate - timedelta(date_range))}')
        print()
        rest = gerrit_rest_obj
        for u_email in self.gerrit_user_accounts:
            try:
                query = ["status:merged"]
                if auth:
                    query += ["owner:" + u_email]
                    # query += ["limit:2"]
                else:
                    query += ["limit:10"]
                changes = rest.get("/changes/?q=%s" % "%20".join(query))
                print(f'{len(changes)} changes')
                # logger.info("%d changes", len(changes))
                count = 0
                repos = list()
                for change in changes:
                    print(f"change_id: {change['change_id']}")
                    print(f"Date created: {change['created']}")
                    print(f"project: {change['project']}")
                    if change['created'].startswith('2019'):
                        create_date = self.get_time(change['created'])
                        expire_days = int((currdate - create_date).days)
                        if expire_days <= date_range:
                            repos.append(change['project']) if change['project'] not in repos else repos
                            count = count + 1
                        else:
                            break
                print(f'User: {self.gerrit_user_accounts[u_email]}')
                print(f'Total Commit(s): {count}')
                print('Repos(s): {}'.format(', '.join(repos)))
                print()
            except RequestException as err:
                logger.error("Error: %s", str(err))

    def gerrit_commit_caller(self, gerrit_auth, gerrit_rest_object, date_range):
        self.get_gerrit_user_account()
        self.generate_gerrit_user_name(gerrit_rest_object)
        self.get_gerrit_rest_data(gerrit_auth, gerrit_rest_object, date_range)


def parse_args():
    parser = argparse.ArgumentParser(description="Get private repos")
    parser.add_argument('--conf',
                        help="Project config category for each private repos",
                        default='projects.ini')
    parser.add_argument('-c', '--gerrit-config', dest='gerrit_config',
                        help='Configuration file for Gerrit',
                        default='patch_via_gerrit.ini')
    parser.add_argument('-d', '--date-range', dest='DATE_RANGE',
                        help='Date range to query',
                        default='7')
    args = parser.parse_args()
    return args


def main():
    """
    Create private ssh repos object and call repo_gen_caller function
    to drive the program
    """

    # Parsing Config file
    configObj = ConfigParse(parse_args())
    configs_dict = configObj.read_projects_config()
    date_range = configObj.DATE_RANGE

    # Gerrit
    gerrit_auth, gerrit_rest = configObj.read_gerrit_config()
    gerritObj = GenerateGerritCommits(configs_dict)
    gerritObj.gerrit_commit_caller(gerrit_auth, gerrit_rest, date_range)


if __name__ == '__main__':
    main()
