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

DATE_RANGE = 90


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


class GenerateGitCommits(ConfigParse):

    def __init__(self, projects_config):
        self.projects_config = projects_config
        # self.git_user_names = list()
        self.gitrepos = {'mobile-testkit': 'couchbaselabs'}
        self.api_url = "https://api.github.com"
        self.username = 'kimtrang'
        self.password = '123Kmn123!'
        self.json_object = None
        self.input_time = None
        self.AUTHORS = {'17035128': 'Sridevi Saragadam', '18100038': 'Hemant Rajput', '46462883': 'Eunice Huang'}

    # def get_git_user_account(self):
    #    for g_group, gitname in self.projects_config.items():
    #        if g_group == 'git-users':
    #            for name in gitnames:
    #                self.git_user_name.append(name)
    #    return self.git_user_names

    def send_request(self, post_data=None):
        if post_data is not None:
            post_data = json.dumps(post_data).encode("utf-8")

        full_url = self.api_url + "/repos/%s/%s/commits?&per_page=100" % (self.git_org, self.git_repo)
        req = urllib.request.Request(full_url, post_data)

        req.add_header("Authorization", b"Basic " + base64.urlsafe_b64encode(self.username.encode("utf-8") + b":" + self.password.encode("utf-8")))

        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        try:
            response = urllib.request.urlopen(req)
            json_data = response.read()
        except urllib.error.HTTPError as error:

            error_details = error.read()
            error_details = json.loads(error_details.decode("utf-8"))

            if error.code in http_error_messages:
                sys.exit(http_error_messages[error.code])
            else:
                error_message = "ERROR: There was a problem with git query.\n%s %s" % (error.code, error.reason)
                if 'message' in error_details:
                    error_message += "\nDETAILS: " + error_details['message']
                sys.exit(error_message)

        with open('git_debug.json', 'w') as fl:
            fl.write(json_data.decode("utf-8"))
        return json.loads(json_data.decode("utf-8"))

    def get_time(self, input_time):
        indate = str(input_time).split('.')
        # pprint(indate)
        input_date = datetime.datetime.strptime(indate[0], '%Y-%m-%dT%H:%M:%SZ')
        return input_date

    def get_git_login_id(self, name):
        for git_author_id, git_author_name in self.AUTHORS.items():
            if name in git_author_name:
                return git_author_id

    def get_git_commits_count(self):
        for repo in self.gitrepos:
            self.git_org = self.gitrepos[repo]
            self.git_repo = repo
            #self.git_unknown_users = defaultdict()

            data = self.send_request()

            currdate = datetime.datetime.utcnow()

            #git_author_ids = self.AUTHORS.keys()
            git_author_names = self.AUTHORS.values()

            print(f'Date Range - {DATE_RANGE}')
            print(f'From Date (UTC): {currdate}')
            print(f'To Date (UCT): {(currdate - timedelta(DATE_RANGE))}')

            for git_author_id, git_author_name in self.AUTHORS.items():
                count = 0
                repos = list()
                for i in data:
                    if i["commit"]["author"]["date"].startswith('2019'):
                        create_date = self.get_time(i["commit"]["author"]["date"])
                        expire_days = int((currdate - create_date).days)
                        # print(f'Delta: {expire_days}')
                        if expire_days <= DATE_RANGE:
                            if i["author"] != None:  # cover no commit's author info case
                                git_creds = str(i["author"]["id"])
                            else:  # default to match their name instead of login id
                                g_name = i["commit"]["author"]["name"]
                                # if g_name in git_author_names:
                                #git_creds = git_author_id
                                git_creds = self.get_git_login_id(g_name)

                            if git_creds == git_author_id:
                                count = count + 1
                                strip_repo_url = re.sub(r"https:\/\/github\.com\/(.*)\/commit.*$", r"\1", i["html_url"])
                                repos.append(strip_repo_url) if strip_repo_url not in repos else repos
                            # else:
                            #    self.git_unknown_users[i["commit"]["author"]["email"]] = i["commit"]["author"]["name"]
                        else:
                            break
                print()
                print(f'User: {git_author_name}')
                print(f'Total Commit(s): {count}')
                print('Repos(s): {}'.format(', '.join(repos)))
                print()

                # if self.git_unknown_users:
                #    print()
                #    print('Found unknown commits:')
                #    print(f'Details: {self.git_unknown_users}')
                #    print()

    def git_commit_caller(self):
        """ Driver function calls for the Git generate commits program"""
        self.get_git_commits_count()


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
        print(f'From Date (UTC): {currdate}')
        print(f'To Date (UTC): {(currdate - timedelta(date_range))}')
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
                # print(f'{len(changes)} changes')
                # logger.info("%d changes", len(changes))
                count = 0
                repos = list()
                for change in changes:
                    # print(f"change_id: {change['change_id']}")
                    # print(f"Date created: {change['created']}")
                    # print(f"project: {change['project']}")
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

    '''def load_json_data(self):
        currdate = datetime.datetime.utcnow()
        print(f'currdate: {currdate}')

        for u_email in self.gerrit_user_accounts:
            fl = 'data/' + u_email + '.json'
            with open(fl) as f:
                data = json.loads(f.read())

            count = 0
            repos = list()
            for i in data:
                if i['created'].startswith('2019'):
                    create_date = self.get_time(i['created'])
                    expire_days = int((currdate - create_date).days)
                    # print(f'Delta: {expire_days}')
                    if expire_days <= DATE_RANGE:
                        repos.append(i['project']) if i['project'] not in repos else repos
                        count = count + 1
                    else:
                        break
            print(f'User: {self.gerrit_user_accounts[u_email]}')
            print(f'Total Commit(s): {count}')
            print('Repos(s): {}'.format(', '.join(repos)))
            print()'''

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
                        default='90')
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
    print('GERRIT Count')
    gerrit_auth, gerrit_rest = configObj.read_gerrit_config()
    gerritObj = GenerateGerritCommits(configs_dict)
    gerritObj.gerrit_commit_caller(gerrit_auth, gerrit_rest, date_range)

    # Git
    print('GIT Count')
    gitObj = GenerateGitCommits(configs_dict)
    gitObj.git_commit_caller()

    # Git
if __name__ == '__main__':
    main()
