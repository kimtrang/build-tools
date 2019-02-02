#!/usr/bin/env python3.6
import argparse
import configparser
import sys

from collections import defaultdict

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

import cbbuild.manifest.info as cb_info
import cbbuild.manifest.parse as cb_parse

from pprint import pprint


def get_project_info(input):
    manifest = cb_parse.Manifest(input)
    manifest_data = manifest.parse_data()
    manifest_info = cb_info.ManifestInfo(manifest_data)
    priv_urls = dict()
    for p in manifest_info.get_projects():
        remote, url = manifest_info.get_project_remote_info(p)
        if url.startswith('ssh'):
            priv_urls[p] = url.replace('ssh://git@', 'https://')

    return priv_urls


def read_projects_config(conf_file):
    ''' Read projects config file to determine the project category
        return dictionary of project category name and list of repo names
        'Analytics': ['cbas', 'cbas-core'] ...
    '''
    projects = []
    projects_config = {}
    config = configparser.ConfigParser(allow_no_value=True)
    try:
        if config.read(conf_file) != []:
            pass
        else:
            raise IOError("Error! Cannot parse %s file!" % conf_file)
    except IOError as error:
        sys.exit(error)
    else:
        project_groups = config.sections()

    for proj in project_groups:
        # list of tuples: [('cbas', ''), ('cbas-core', '')]
        projects_tuples = config.items(proj)
        projects = [x[0] for x in projects_tuples]
        projects_config[proj] = projects
    return projects_config
    # return {pgroup: config[pgroup] for pgroup in project_groups}


def generate_report(config, priv_path_repo, outfile):
    '''Generate report text file '''
    project_url = defaultdict(list)
    projects = read_projects_config(config)
    ''' Mapping private repo names against projects.ini category
        return dictionary private repo urls and project category name
        'http://github.com/couchbase/backup': 'Backup',
        'http://github.com/couchbase/cbas-core': 'Analytics'
        'http://github.com/couchbase/cbas': 'Analytics', ...
    '''
    print(type(projects))
    pprint(projects)
    for repo in priv_path_repo:
        for proj, proj_config_repos in projects.items():
            if repo in proj_config_repos:
                project_url[priv_path_repo[repo]] = proj

    pprint(project_url)
    ''' Check if repos has not been define in project config category
        bailed out so private repos can be added to category in projects.ini
    '''
    repo_names = sorted(priv_path_repo.keys())
    lists_of_projects = sorted(projects.values())
    # flatten out the lists_of_projects in projects.ini
    proj_flat_list = [item for llist in lists_of_projects for item in llist]
    found_missing_products = set(repo_names).difference(proj_flat_list)
    if found_missing_products:
        print("\n\n")
        print("=== Found private repos missing in %s! ===" % config)
        print("=== Please add the missing repo(s) in %s file ===!" % config)
        print('\n'.join(found_missing_products))
        sys.exit(1)

    # Generate report
    reverse_project_url = {}
    for key, value in project_url.items():
        reverse_project_url.setdefault(value, set()).add(key)
    with open(outfile, 'w') as fh:
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
    ''' List all files in gdrive folders
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
                print("AM I IN FOLDER IF?")
                filelist.append({"id": f['id'], "title": f['title'], "list": ListFolder(f['id'])})
            else:
                print("AM I IN FOLDER ELSE?")
                filelist[f['title']] = f['id']
    return filelist


def gdrive_upload(drive, gdrive_files, folder_id, upload_file):
    ''' Upload to a folder
        if file already existed, remove them and re-upload
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
                print('File uploaded successfully!')
                print('title: {}, id: {}'.format(gfile['title'], gfile['id']))
    else:
        ''' Upload file to empty folder '''
        try:
            gfile = drive.CreateFile({"parents": [{"kind": "drive#fileLink", "id": folder_id}]})
            gfile.SetContentFile(upload_file)
            gfile.Upload()
        except:
            raise
        else:
            print('File uploaded successfully!')
            print('title: {}, id: {}'.format(gfile['title'], gfile['id']))


def main(args):
    output_file = f'{args.release}.txt'
    private_remote_path = get_project_info(args.input)
    print(private_remote_path)
    generate_report(args.conf, private_remote_path, output_file)
    # Upload to gdrive
    drive = g_authenticate()
    filelist = ListFolder(args.folder_id, drive)
    pprint(filelist)
    #gdrive_upload(drive, filelist, args.folder_id, output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get private repos\n\n")
    parser.add_argument('--input',
                        help="Input manifest file\n\n", required=True)
    parser.add_argument('--release',
                        help="Release name\n", default='mad-hatter',
                        required=True)
    parser.add_argument('--folder_id',
                        help="Pre-defined google folder id with proper group permission\n", default='157tLwbGuKLxKAbeG7RyO1gv5GC20TgNa',
                        required=False)
    parser.add_argument('--conf',
                        help="Project config category for each private repos\n", default='projects.ini',
                        required=False)

    args = parser.parse_args()
    main(args)
