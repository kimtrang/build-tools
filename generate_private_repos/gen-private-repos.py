#!/usr/bin/env python3.6

import argparse
import configparser
from collections import defaultdict
from lxml import etree
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
import sys
from pprint import pprint


def initialize_etree(input):
    ''' parse manifest to get ssh remote '''
    tree = etree.parse(input)
    return tree


def get_remote(tree):
    ''' Parse manifest to get ssh remote
        It could be more than one ssh remote url
        return private_remote dictionary
        'couchbase-priv': 'ssh://git@github.com/...'
    '''
    private_remote = {}
    remote_node = tree.iterfind("//remote")

    for remote in remote_node:
        remote_name = remote.get('name')
        remote_fetch = remote.get('fetch', remote_name)
        if 'ssh' in remote_fetch:
            private_remote[remote_name] = remote_fetch
    return private_remote


def get_repos(remotes, tree):
    ''' Parse manifest to get all private repo names
        return dictionary of repos with remote name
        'voltron': 'couchbase-priv' ...
    '''
    private_repos = {}
    projects = tree.iterfind("//project")

    remote_names = remotes.keys()
    for proj in projects:
        proj_name = proj.get('name')
        proj_remote = proj.get('remote', proj_name)
        for remote in remote_names:
            if remote == proj_remote:
                private_repos[proj_name] = proj_remote
    return private_repos


def generate_remote_path(repos, remotes):
    ''' get remote ssh:// translate to http:// '''
    remote_path = {}
    for url in remotes:
        remote_path[url] = remotes[url].replace('ssh://git@', 'http://')
    return remote_path


def read_projects_config(conf_file):
    ''' Read projects config file to determine the project category
        return dictionary of project category name and list of repo names
        'Analytics': ['cbas', 'cbas-core'] ...
    '''
    projects = []
    config = configparser.ConfigParser(allow_no_value=True)
    try:
        if config.read(conf_file) != []:
            pass
        else:
            raise IOError("Error! Cannot parse %s file!" % conf_file)
    except IOError as error:
        sys.exit(error)
    else:
        projects = config.sections()
        projects_config = {}

    for proj in projects:
        proj_list = []
        for key in config[proj]:
            proj_list.append(key)
        projects_config[proj] = proj_list
    return projects_config


def generate_report(config, repos, rpath, outfile):
    '''Generate report text file '''
    project_url = defaultdict(list)
    projects = read_projects_config(config)
    ''' Mapping private repo names against projects.ini category
        return dictionary private repo urls and project category name
        'http://github.com/couchbase/backup': 'Backup',
        'http://github.com/couchbase/cbas-core': 'Analytics'
        'http://github.com/couchbase/cbas': 'Analytics', ...
    '''
    for repo in repos:
        for proj, proj_config_repos in projects.items():
            if repo in proj_config_repos:
                project_url[rpath[repos[repo]] + repo] = proj

    ''' Check if repos has not been define in project config category
        bailed out so private repos can be added to category in projects.ini
    '''
    repo_names = sorted(repos.keys())
    lists_of_projects = sorted(projects.values())
    # flatten out the lists_of_projects in projects.ini
    proj_flat_list = [item for llist in lists_of_projects for item in llist]
    found_missing_products = set(repo_names).difference(proj_flat_list)
    if found_missing_products:
        print("=== Found private repos missing in project.ini! ===")
        print("Please add these repos in project.ini!")
        print('\n'.join(found_missing_products))
        sys.exit(1)

    # Generate report
    reverse_project_url = {}
    for key, value in project_url.items():
        reverse_project_url.setdefault(value, set()).add(key)
    # pprint(reverse_project_url)
    with open(outfile, 'a+') as fh:
        for proj in reverse_project_url:
            fh.write("=== {} ===\n".format(proj))
            fh.write('\n'.join(reverse_project_url[proj]))
            fh.write("\n\n")


def g_authenticate():
    ''' Authenticate to google drive api
        return drive
    '''
    gauth = GoogleAuth()
    gauth.LocalWebserverAuth()
    drive = GoogleDrive(gauth)
    return drive


def ListFolder(parent_folderid, drive):
    ''' List all files in gdrive folders and
        save to filelist dictionary
        filename: file_id
    '''
    filelist = {}
    try:
        file_list = drive.ListFile({'q': "'%s' in parents and trashed=false" % parent_folderid}).GetList()
    except:
        raise
    else:
        for f in file_list:
            if f['mimeType'] == 'application/vnd.google-apps.folder':  # if folder
                filelist.append({"id": f['id'], "title": f['title'], "list": ListFolder(f['id'])})
            else:
                filelist[f['title']] = f['id']
    return filelist


def gdrive_upload(drive, gdrive_files, folder_id, upload_file):
    ''' Upload to a folder
        if file already existed, remove them
    '''
    if gdrive_files:
        for fname, fid in gdrive_files.items():
            if upload_file == fname:
                try:
                    gfile = drive.CreateFile({'id': fid})
                    gfile.Trash()
                except:
                    raise
        else:
            try:
                gfile = drive.CreateFile({"parents": [{"kind": "drive#fileLink", "id": folder_id}]})
                gfile.SetContentFile(upload_file)
                gfile.Upload()
            except:
                raise
            else:
                print('File uploaded, title: {}, id: {}'.format(gfile['title'], gfile['id']))
    else:
        ''' Upload file to empty folder '''
        try:
            gfile = drive.CreateFile({"parents": [{"kind": "drive#fileLink", "id": folder_id}]})
            gfile.SetContentFile(upload_file)
            gfile.Upload()
        except:
            raise
        else:
            print('File uploaded, title: {}, id: {}'.format(gfile['title'], gfile['id']))


def main(args):
    output_file = f'{args.release}.txt'
    tree = initialize_etree(args.input)
    remotes = get_remote(tree)
    repos = get_repos(remotes, tree)
    private_remote_path = generate_remote_path(repos, remotes)
    generate_report(args.conf, repos, private_remote_path, output_file)
    # Upload to gdrive
    drive = g_authenticate()
    filelist = ListFolder(args.folder_id, drive)
    gdrive_upload(drive, filelist, args.folder_id, output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get private repos\n\n")
    parser.add_argument('--input',
                        help="Input manifest file\n\n", required=True)
    parser.add_argument('--release',
                        help="Output file base on product name\n", default='mad-hatter',
                        required=True)
    parser.add_argument('--folder_id',
                        help="Pre-defined folder_id with proper group permission\n", default='157tLwbGuKLxKAbeG7RyO1gv5GC20TgNa',
                        required=False)
    parser.add_argument('--conf',
                        help="Project config category for each private repos\n", default='projects.ini',
                        required=False)

    args = parser.parse_args()
    main(args)
