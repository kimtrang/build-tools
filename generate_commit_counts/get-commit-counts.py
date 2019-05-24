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
        self.project_gerrit_config = list()
        self.project_git_config = defaultdict()
        self.conf = args.conf
        self.gerrit_config = args.gerrit_config
        self.git_config = args.git_config
        self.DATE_RANGE = int(args.DATE_RANGE)

    def read_projects_config(self):
        """
        Read projects config file to determine Gerrit or Git users info.
        Return list of Gerrit users (me@couchbase.com)
        Return dictionary of Git users (git_login_id:full_name)
        """
        config = configparser.ConfigParser(allow_no_value=True)
        if config.read(self.conf):
            for section_name in config.sections():
                if section_name == 'gerrit-users':
                    self.project_gerrit_config = config.options(section_name)
                elif section_name == 'git-users':
                    for gid, gname in config.items(section_name):
                        self.project_git_config[gid] = gname
        return self.project_gerrit_config, self.project_git_config

    def read_git_config(self):
        """
            Read Git config and return git_url, user and passwd
        """
        git_config = configparser.ConfigParser()
        git_config.read(self.git_config)

        if 'main' not in git_config.sections():
            print(
                'Invalid or unable to read config file "{}"'.format(
                    self.git_config
                )
            )
            sys.exit(1)
        try:
            git_url = git_config.get('main', 'git_url')
            user = git_config.get('main', 'username')
            passwd = git_config.get('main', 'password')
        except configparser.NoOptionError:
            print(
                'One of the options is missing from the config file: '
                'git_url, username, password.  Aborting...'
            )
            sys.exit(1)
        return git_url, user, passwd

    def read_gerrit_config(self):
        """
            Read Gerrit config and return Gerrit Rest object
        """
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

    def __init__(self, project_git_config):
        self.project_git_config = project_git_config
        pprint(project_git_config)
        self.gitrepos = {'mobile-testkit': 'couchbaselabs'}

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
        for git_author_id, git_author_name in self.project_git_config.items():
            if name in git_author_name:
                return git_author_id

    def generate_gitid_data(self, gid, item, data_dict):
        if gid in data_dict:
            data_dict[gid].append(item)
        else:
            data_dict[gid] = [item]
        return data_dict

    def get_git_commits_count(self, git_url, git_user, git_passwd, date_range):
        for repo in self.gitrepos:
            self.api_url = git_url
            self.username = git_user
            self.password = git_passwd
            self.git_org = self.gitrepos[repo]
            self.git_repo = repo
            self.git_unknown_users = defaultdict()

            data = self.send_request()

            currdate = datetime.datetime.utcnow()
            print(f'Date Range - {date_range}')
            print(f'From Date (UTC): {currdate}')
            print(f'To Date (UCT): {(currdate - timedelta(date_range))}')

            commits_counts = defaultdict()
            commits_repos = defaultdict(set)
            commits_message = defaultdict()
            repos = list()
            # print(f'Total SHA {len(data)}')
            print()
            for i in data:
                if i["commit"]["author"]["date"].startswith('2019'):
                    # print(f'SHA: {i["sha"]}')
                    create_date = self.get_time(i["commit"]["author"]["date"])
                    expire_days = (currdate - create_date).days
                    # print(f'Delta: {expire_days}')
                    if expire_days <= date_range:
                        if i["author"] != None:  # cover no commit's author info case
                            git_creds = str(i["author"]["id"])
                        elif i["commit"]["author"]["name"]:
                            g_name = i["commit"]["author"]["name"]
                            git_creds = self.get_git_login_id(g_name)
                        else:
                            print(f'Cannot find valid author for this commit: {i["sha"]} - {i["html_url"]}')
                            git_unknown_users[i["sha"]].add(i["html_url"])

                        self.generate_gitid_data(git_creds, i["sha"], commits_counts)
                        strip_repo_url = re.sub(r"https:\/\/github\.com\/(.*)\/commit.*$", r"\1", i["html_url"])
                        repos.append(strip_repo_url) if strip_repo_url not in repos else repos
                        commits_repos[git_creds].add(strip_repo_url)  # this is check if other repos
                        self.generate_gitid_data(git_creds, i["sha"] + ' -- ' + i["commit"]["message"], commits_message)

                    else:
                        break

            for git_author_id, git_author_name in self.project_git_config.items():
                if git_author_id in commits_counts.keys():
                    total_commits = len(commits_counts[git_author_id])
                    commit_messages = commits_message[git_author_id]
                    repos = commits_repos[git_author_id]
                else:
                    total_commits = 0
                    commit_messages = ''
                    repos = ''

                print(f'User: {git_author_name}')
                print(f'Total Commit(s): {total_commits}')
                print('Repos(s): ' + '\n'.join(map(str, repos)))
                print('Commit Messages:')
                print('\n'.join(map(str, commit_messages)))
                print()
                print()

            if self.git_unknown_users:
                print()
                print('WARNING!  Found unknown commits:')
                print(f'Details: {self.git_unknown_users}')
                print()
                sys.exit(1)

    def git_commit_caller(self, git_url, api_user, api_passwd, date_range):
        """ Driver function calls for the Git generate commits program"""
        self.get_git_commits_count(git_url, api_user, api_passwd, date_range)


class GenerateGerritCommits(ConfigParse):
    def __init__(self, project_gerrit_config):
        self.gerrit_user_emails = project_gerrit_config
        self.gerrit_user_accounts = defaultdict()
        self.project_gerrit_config = project_gerrit_config

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
                # logger.error("Error: %s", str(err))
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
                commit_subjects = list()
                for change in changes:
                    # print(f"change_id: {change['change_id']}")
                    # print(f"Date created: {change['created']}")
                    # print(f"project: {change['project']}")
                    if change['created'].startswith('2019'):
                        create_date = self.get_time(change['created'])
                        expire_days = int((currdate - create_date).days)
                        if expire_days <= date_range:
                            repos.append(change['project']) if change['project'] not in repos else repos
                            message = change['change_id'] + ' -- ' + change['subject']
                            commit_subjects.append(message)
                            count = count + 1
                        else:
                            break
                print(f'User: {self.gerrit_user_accounts[u_email]}')
                print(f'Total Commit(s): {count}')
                print('Repos(s): {}'.format(', '.join(repos)))
                print('Commit Messages:')
                print('\n'.join(map(str, commit_subjects)))
                print()
            except RequestException as err:
                logger.error("Error: %s", str(err))

    def gerrit_commit_caller(self, gerrit_auth, gerrit_rest_object, date_range):
        # self.get_gerrit_user_account()
        self.generate_gerrit_user_name(gerrit_rest_object)
        self.get_gerrit_rest_data(gerrit_auth, gerrit_rest_object, date_range)


def parse_args():
    parser = argparse.ArgumentParser(description="Get private repos")
    parser.add_argument('--conf',
                        help="Project config category for each private repos",
                        default='projects.ini')
    parser.add_argument('-gerrit-config', '--gerrit-config', dest='gerrit_config',
                        help='Configuration file for Gerrit',
                        default='patch_via_gerrit.ini')
    parser.add_argument('-git-config', '--git-config', dest='git_config',
                        help='Configuration file for Git API',
                        default='git_committer.ini')
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
    gerrit_user_emails, git_users = configObj.read_projects_config()
    date_range = configObj.DATE_RANGE

    # Gerrit # Need to fix projects_config
    print('GERRIT Count')
    gerrit_auth, gerrit_rest = configObj.read_gerrit_config()
    gerritObj = GenerateGerritCommits(gerrit_user_emails)
    gerritObj.gerrit_commit_caller(gerrit_auth, gerrit_rest, date_range)

    # Git
    print('GIT Count')
    git_url, api_user, api_passwd = configObj.read_git_config()
    gitObj = GenerateGitCommits(git_users)
    gitObj.git_commit_caller(git_url, api_user, api_passwd, date_range)

    # Git
if __name__ == '__main__':
    main()
