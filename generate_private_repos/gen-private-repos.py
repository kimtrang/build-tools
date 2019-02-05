#!/usr/bin/env python3.6

import argparse
import configparser
import sys

from collections import defaultdict

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from pydrive.files import ApiRequestError, FileNotUploadedError

import cbbuild.manifest.info as cb_info
import cbbuild.manifest.parse as cb_parse


class PrivateReposGen:
    """Generate a list of private ssh repos to a text file and upload to google drive"""

    def __init__(self, args):
        # Require args definition
        self.input_manifest = args.input_manifest
        self.release = args.release
        self.folder_id = args.folder_id
        self.conf = args.conf
        self.upload_file = f'{args.release}.txt'
        self.priv_urls = dict()
        self.projects = dict()
        self.projects_config = dict()
        self.gdrive = list()
        self.gfolder_filelist = dict()

    def get_project_info(self):
        """Return dictionary of project_name with project git link
            'backup': 'https://github.com/couchbase/backup.git',
            'cbftx': 'https://github.com/couchbase/cbftx.git'"""
        manifest = cb_parse.Manifest(self.input_manifest)
        manifest_data = manifest.parse_data()
        manifest_info = cb_info.ManifestInfo(manifest_data)
        for p in manifest_info.get_projects():
            remote, url = manifest_info.get_project_remote_info(p)
            if url.startswith('ssh'):
                self.priv_urls[p] = url.replace('ssh://git@', 'https://')

    def read_projects_config(self):
        """Read projects config file to determine the project category
        return dictionary of project category name and list of repo names
        'Analytics': ['cbas', 'cbas-core'], 'Backup': ['backup'] ..."""
        projects = []
        config = configparser.ConfigParser(allow_no_value=True)
        if config.read(self.conf):
            project_group = config.sections()
        else:
            sys.exit(f'Error! Cannot parse {self.conf} file!')

        for proj in project_group:
            # The following generates a list of tuples: [('cbas', ''), ('cbas-core', '')]
            project_info = config.items(proj)
            proj_names = [t[0] for t in project_info]
            self.projects_config[proj] = proj_names

    def generate_report(self):
        """Generate report text file"""
        project_url = defaultdict(list)
        # Mapping private repo names against projects.ini's category repos name.  Return dictionary private repo urls and project category name
        #    'http://github.com/couchbase/backup.git': 'Backup',
        #    'http://github.com/couchbase/cbas-core.git': 'Analytics'
        #    'http://github.com/couchbase/cbas.git': 'Analytics', ...
        for proj_name, proj_url in self.priv_urls.items():
            for p_group, p_git_urls in self.projects_config.items():
                if proj_name in p_git_urls:
                    project_url[self.priv_urls[proj_name]] = p_group

        # Check if private repo(s) found in manifest.xml is missing from project group in args.conf
        repo_names = sorted(self.priv_urls.keys())
        project_list = sorted(set(item for plist in self.projects_config.values() for item in plist))
        found_missing_products = set(repo_names).difference(project_list)
        if found_missing_products:
            print("\n\n=== Found private repos missing in %s! ===" % self.conf)
            print("    Please add the missing repo(s) in %s file!" % self.conf)
            print('\n'.join(found_missing_products))
            print()
            sys.exit(1)

        # Generate report
        reverse_project_url = defaultdict(set)
        for key, value in project_url.items():
            reverse_project_url[value].add(key)
        with open(self.upload_file, 'w') as fh:
            for proj in reverse_project_url:
                fh.write("=== {} ===\n".format(proj))
                fh.write('\n'.join(reverse_project_url[proj]))
                fh.write("\n\n")

    def g_authenticate(self):
        """Authenticate to google drive api
            return drive
        """
        gauth = GoogleAuth()
        gauth.LocalWebserverAuth()
        self.gdrive = GoogleDrive(gauth)

    def g_listfolder(self):
        """List all files in gdrive folders
            save to filelist dictionary
            filename: file_id
        """
        file_list = list()
        try:
            file_list = self.gdrive.ListFile({'q': "'%s' in parents and trashed=false" % self.folder_id}).GetList()
        except ApiRequestError as exc:
            raise RuntimeError(exc.message)
        else:
            for f in file_list:
                self.gfolder_filelist[f['title']] = f['id']

    def gdrive_upload(self):
        """Upload to a folder.  If file already existed, remove them and re-upload"""
        if self.gfolder_filelist:
            for fname, fid in self.gfolder_filelist.items():
                if self.upload_file == fname:
                    try:
                        gfile = self.gdrive.CreateFile({'id': fid})
                        gfile.Trash()
                    except ApiRequestError as exc:
                        raise RuntimeError(exc.message)
            else:
                try:
                    gfile = self.gdrive.CreateFile({"parents": [{"kind": "drive#fileLink", "id": self.folder_id}]})
                    gfile.SetContentFile(self.upload_file)
                    gfile.Upload()
                except FileNotUploadedError as exc:
                    raise RuntimeError(exc.message)
                else:
                    print('File uploaded successfully!')
                    print('title: {}, id: {}'.format(gfile['title'], gfile['id']))
        else:
            # Upload file to empty folder
            try:
                gfile = self.gdrive.CreateFile({"parents": [{"kind": "drive#fileLink", "id": self.folder_id}]})
                gfile.SetContentFile(self.upload_file)
                gfile.Upload()
            except FileNotUploadedError as exc:
                raise RuntimeError(exc.message)
            else:
                print('File uploaded successfully!')
                print('title: {}, id: {}'.format(gfile['title'], gfile['id']))

    def repo_gen_caller(self):
        self.get_project_info()
        self.read_projects_config()
        self.generate_report()
        self.g_authenticate()
        self.g_listfolder()
        self.gdrive_upload()


def parse_args():
    parser = argparse.ArgumentParser(description="Get private repos\n\n")
    parser.add_argument('--input-manifest',
                        help="Input manifest file\n\n", required=True)
    parser.add_argument('--release',
                        help="Release name\n", default='mad-hatter',
                        required=True)
    parser.add_argument('--folder-id',
                        help="Pre-defined google folder id with proper group permission\n")
    parser.add_argument('--conf',
                        help="Project config category for each private repos\n", default='projects.ini')
    args = parser.parse_args()

    return args


def main():
    """Create private ssh repos object and call repo_gen_caller function to drive the program"""

    private_repos_project = PrivateReposGen(parse_args())
    private_repos_project.repo_gen_caller()


if __name__ == '__main__':
    main()
